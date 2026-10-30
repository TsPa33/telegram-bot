"""Real disposable PostgreSQL only: order lifecycle, ownership, replay and races."""
from concurrent.futures import ThreadPoolExecutor
from subprocess import run
from uuid import uuid4
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db import engine
from conftest import signup


def key():return {'request_key':str(uuid4())}


def buyer(c,**extra):
    r=c.post('/api/v1/buyers',json={'name':'Покупець','phone':'+38 (050) 123-45-67',**extra})
    assert r.status_code==201,r.text
    return r.json()


def stocked(c,vehicle,quantity=3,**extra):
    r=c.post('/api/v1/parts',json={'name':'Капот','vehicle_id':vehicle['id'],'selling_price':'999.99',**extra});assert r.status_code==201,r.text
    part=r.json();r=c.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'receipt','quantity':quantity,'reason':'Local order fixture'})
    assert r.status_code==200,r.text
    return part


def line(part,quantity=1,**extra):return {'part_id':part['id'],'quantity':quantity,'unit_price':'123.45','currency':'UAH',**extra}


def create(c,b,items,**extra):
    r=c.post('/api/v1/orders',json={**key(),'buyer_id':b['id'],'lines':items,**extra});assert r.status_code==201,r.text
    return r.json()


def action(c,order,name,body=None):return c.post('/api/v1/orders/'+order['id']+'/'+name,json=body or key())


def state(c,part):return c.get('/api/v1/parts/'+part['id'],headers={'X-Warehouse-Client':'5'}).json()


@pytest.fixture
def setup(logged,vehicle):
    b=buyer(logged);p=stocked(logged,vehicle)
    return logged,b,p


def test_buyer_search_normalization_update_and_validation(logged):
    b=buyer(logged,additional_phone='00380 67 555 44 33')
    assert b['phone']=='+38 (050) 123-45-67' and b['phone_normalized']=='380501234567'
    for phone in ['0501234567','+380501234567','123-45','0675554433']:
        r=logged.get('/api/v1/buyers',params={'phone':phone});assert r.status_code==200 and r.json()['total']==1
    assert logged.get('/api/v1/buyers',params={'phone':'abc'}).status_code==422
    assert logged.post('/api/v1/buyers',json={'name':'Invalid','phone':'abcdefg'}).status_code==422
    r=logged.put('/api/v1/buyers/'+b['id'],json={'name':'Оновлений','phone':'0501234567','notes':'Примітка'})
    assert r.status_code==200 and r.json()['notes']=='Примітка'
    assert logged.get('/api/v1/buyers/'+b['id']).json()['name']=='Оновлений'


def test_creation_multicurrency_search_snapshot_and_no_stock_change(setup,vehicle):
    c,b,p=setup;second=stocked(c,vehicle,name='Двері')
    before=state(c,p)
    order=create(c,b,[line(p,2),line(second,unit_price='0.01',currency='USD')])
    assert order['number']==1 and order['status']=='new' and order['sold_at'] is None
    assert order['totals_by_currency']=={'UAH':'246.90','USD':'0.01'}
    assert state(c,p)==before and order['reservations']==[]
    first=next(row for row in order['lines'] if row['part_id']==p['id'])
    assert first['name']=='Капот' and first['donor_snapshot']['manufacturer']==vehicle['manufacturer']
    assert c.get('/api/v1/orders',params={'phone':'0501234567'}).json()['total']==1
    assert c.get('/api/v1/orders',params={'q':'№1'}).json()['total']==1
    assert c.get('/api/v1/orders',params={'q':'12345'}).json()['total']==1
    assert c.get('/api/v1/orders',params={'number':2}).json()['total']==0
    c.patch('/api/v1/parts/'+p['id']+'/price',json={'selling_price':'500','currency':'USD'})
    assert c.get('/api/v1/orders/'+order['id']).json()['totals_by_currency']==order['totals_by_currency']
    assert c.get('/api/v1/orders/'+order['id']).json()['lines'][0]['name']
    assert c.get('/api/v1/orders/readiness').json()['contract_version']==6
    assert c.get('/api/v1/sales-workspace/readiness').json()['contract_version']==5


def test_reserve_legacy_guard_release_cancel_and_sale_from_reserve(setup):
    c,b,p=setup
    url='/api/v1/parts/'+p['id']+'/operations'
    assert c.post(url,json={'type':'reserve','quantity':1,'reason':'Old manual reservation'}).status_code==200
    order=create(c,b,[line(p)])
    reserve_key=key();r=action(c,order,'reserve',reserve_key);assert r.status_code==200,r.text
    assert r.json()['status']=='reserved' and len(r.json()['reservations'])==1
    assert action(c,order,'reserve',reserve_key).json()==r.json()
    assert state(c,p)['quantity']==3 and state(c,p)['reserved_quantity']==2
    # Only the old, unassigned reservation may be released through v5.
    assert c.post(url,json={'type':'release','quantity':2,'reason':'Cannot steal reservation'}).status_code==409
    assert c.post(url,json={'type':'release','quantity':1,'reason':'Release old manual'}).status_code==200
    assert c.post(url,json={'type':'release','quantity':1,'reason':'Cannot release assigned'}).status_code==409
    release_key=key();assert action(c,order,'release',release_key).status_code==200
    assert action(c,order,'release',release_key).status_code==200
    assert state(c,p)['reserved_quantity']==0
    assert action(c,order,'reserve').status_code==200
    sale_key=key();r=action(c,order,'sell',sale_key);assert r.status_code==200,r.text
    assert r.json()['sold_at'] and r.json()['reservations']==[]
    assert action(c,order,'sell',sale_key).json()==r.json()
    assert action(c,order,'sell').status_code==409
    assert state(c,p)['quantity']==2 and state(c,p)['reserved_quantity']==0
    assert state(c,p)['selling_price']=='999.99'  # Agreed price never overwrites the stock card.
    ev=c.get('/api/v1/orders/'+order['id']+'/events').json()['items']
    sale=next(e for e in ev if e['type']=='sale_confirmed')
    assert sale['data']['lines'][0]['unit_price']=='123.45'
    assert sale['data']['lines'][0]['sale_operation_id']
    assert c.get('/api/v1/audit',params={'part_id':p['id'],'type':'sale'}).json()['total']==1


def test_cancel_releases_only_own_reserves(setup):
    c,b,p=setup;one=create(c,b,[line(p)]);two=create(c,b,[line(p)])
    assert action(c,one,'reserve').status_code==action(c,two,'reserve').status_code==200
    assert action(c,one,'cancel').json()['status']=='cancelled'
    assert state(c,p)['quantity']==3 and state(c,p)['reserved_quantity']==1
    assert action(c,one,'cancel').status_code==200
    assert action(c,one,'sell').status_code==409
    assert action(c,two,'sell').status_code==200
    assert state(c,p)['quantity']==2 and state(c,p)['reserved_quantity']==0


def test_status_shipping_is_not_sale_and_completion_requires_explicit_sale(setup):
    c,b,p=setup;order=create(c,b,[line(p)])
    for bad in ['reserved','completed','cancelled','new','shipped']:
        assert action(c,order,'status',{**key(),'status':bad}).status_code==409
    assert action(c,order,'reserve').status_code==200
    assert action(c,order,'status',{**key(),'status':'shipped'}).json()['status']=='shipped'
    assert state(c,p)['quantity']==3 and state(c,p)['reserved_quantity']==1
    assert action(c,order,'status',{**key(),'status':'completed'}).status_code==409
    assert action(c,order,'sell').status_code==200
    assert action(c,order,'status',{**key(),'status':'completed'}).json()['status']=='completed'
    assert action(c,order,'cancel').status_code==409


def test_lines_delivery_contacts_and_immutable_events(setup,vehicle):
    c,b,p=setup;order=create(c,b,[line(p)])
    events_before=c.get('/api/v1/orders/'+order['id']+'/events').json()['items']
    url='/api/v1/orders/'+order['id']
    assert c.patch(url,json={**key(),'delivery_method':'branch'}).status_code==422
    r=c.patch(url,json={**key(),'delivery_method':'branch','city':'Київ','delivery_address':'Відділення 1'})
    assert r.status_code==200,r.text
    assert c.patch(url,json={**key(),'tracking_number':'TEST-LOCAL'}).json()['city']=='Київ'
    assert c.patch(url,json={**key(),'contact_phone':'0675554433','notes':'Call buyer'}).status_code==200
    assert c.get('/api/v1/orders',params={'phone':'0675554433'}).json()['total']==1
    replacement={**key(),'lines':[line(p,2,unit_price='10.01',currency='USD')]}
    assert c.put(url+'/lines',json=replacement).json()['totals_by_currency']=={'USD':'20.02'}
    assert c.put(url+'/lines',json=replacement).status_code==200
    assert action(c,order,'reserve').status_code==200
    assert c.put(url+'/lines',json={**replacement,**key()}).status_code==409
    assert action(c,order,'release').status_code==200
    # Former lines/reservations must survive edits, never cascade-delete history.
    assert c.put(url+'/lines',json={**replacement,**key()}).status_code==200
    assert action(c,order,'sell').status_code==200
    assert c.put(url+'/lines',json={**replacement,**key()}).status_code==409
    assert c.patch(url,json={**key(),'buyer_id':buyer(c,phone='0671112233')['id']}).status_code==409
    events_after=c.get(url+'/events',params={'limit':200}).json()['items']
    assert all(event in events_after for event in events_before)


def test_transaction_rolls_back_multi_line_reserve_and_sale(setup,vehicle):
    c,b,p=setup;short=stocked(c,vehicle,quantity=1,name='Short')
    order=create(c,b,[line(p),line(short,2)])
    assert action(c,order,'reserve').status_code==409
    assert state(c,p)['quantity']==3 and state(c,p)['reserved_quantity']==0
    assert action(c,order,'sell').status_code==409
    assert state(c,p)['quantity']==3
    assert c.get('/api/v1/audit',params={'part_id':p['id'],'type':'sale'}).json()['total']==0
    assert c.get('/api/v1/orders/'+order['id']).json()['status']=='new'


@pytest.mark.parametrize('operation',['reserve','sell'])
def test_concurrent_same_key_replays_and_last_unit_only_once(setup,operation):
    c,b,p=setup;order=create(c,b,[line(p,3)]);body=key()
    def send(_):
        with TestClient(app) as other:
            other.cookies.update(dict(c.cookies));other.headers.update(dict(c.headers))
            r=action(other,order,operation,body);return r.status_code,r.json()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,range(2)))
    assert results[0][0]==results[1][0]==200 and results[0][1]==results[1][1]
    other=create(c,b,[line(p)])
    assert action(c,other,operation).status_code==409
    assert state(c,p)['quantity']==(0 if operation=='sell' else 3)
    assert state(c,p)['reserved_quantity']==(3 if operation=='reserve' else 0)


def test_concurrent_different_keys_order_creation_and_order_sale_vs_legacy(setup):
    c,b,p=setup;payload={**key(),'buyer_id':b['id'],'lines':[line(p,3)]}
    one=c.post('/api/v1/orders',json=payload);assert one.status_code==201
    assert c.post('/api/v1/orders',json=payload).json()==one.json()
    assert c.post('/api/v1/orders',json={**payload,'notes':'Different payload'}).status_code==409
    order=one.json()
    def send(mode):
        with TestClient(app) as other:
            other.cookies.update(dict(c.cookies));other.headers.update(dict(c.headers))
            if mode=='legacy':return other.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'sale','quantity':3}).status_code
            return action(other,order,'sell').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(send,['order','legacy']))
    assert sorted(codes)==[200,409]
    assert state(c,p)['quantity']==0


def test_auth_csrf_isolation_and_validation(setup):
    c,b,p=setup;order=create(c,b,[line(p)])
    with TestClient(app) as other:
        assert other.get('/api/v1/orders').status_code==401
        assert other.get('/api/v1/orders/readiness').status_code==401
        signup(other,'other-orders@example.test')
        assert other.get('/api/v1/buyers/'+b['id']).status_code==404
        assert other.get('/api/v1/orders/'+order['id']).status_code==404
        assert other.get('/api/v1/orders/'+order['id']+'/events').status_code==404
        assert action(other,order,'sell').status_code==404
        assert other.get('/api/v1/buyers',params={'phone':b['phone']}).json()['total']==0
        assert other.get('/api/v1/orders',params={'phone':b['phone']}).json()['total']==0
        assert other.post('/api/v1/orders',json={**key(),'buyer_id':b['id'],'lines':[line(p)]}).status_code==404
        local_buyer=buyer(other)
        assert other.post('/api/v1/orders',json={**key(),'buyer_id':local_buyer['id'],'lines':[line(p)]}).status_code==404
    for changes in [{'quantity':0},{'quantity':-1},{'unit_price':'-1'},{'unit_price':'1.001'},{'currency':'EUR'}]:
        assert c.post('/api/v1/orders',json={**key(),'buyer_id':b['id'],'lines':[line(p,**changes)]}).status_code==422
    assert c.post('/api/v1/orders',json={**key(),'buyer_id':b['id'],'lines':[line(p),line(p)]}).status_code==422
    c.headers.pop('X-CSRF-Token')
    assert action(c,order,'reserve').status_code==403
    assert c.post('/api/v1/buyers',json={'name':'No CSRF','phone':'0501234567'}).status_code==403


def test_migration_preserves_v5_data_and_refuses_destructive_downgrade(logged,vehicle):
    c=logged;p=stocked(c,vehicle)
    c.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'reserve','quantity':1,'reason':'Preexisting legacy reserve'})
    with engine().connect() as db:
        before=db.execute(text('SELECT row_to_json(p) FROM parts p')).scalars().all()
        audit=db.execute(text('SELECT row_to_json(o) FROM operations o ORDER BY id')).scalars().all()
    run([sys.executable,'-m','alembic','downgrade','c24a9b71e603'],check=True)
    run([sys.executable,'-m','alembic','upgrade','head'],check=True)
    with engine().connect() as db:
        assert db.execute(text('SELECT row_to_json(p) FROM parts p')).scalars().all()==before
        assert db.execute(text('SELECT row_to_json(o) FROM operations o ORDER BY id')).scalars().all()==audit
        assert db.execute(text('SELECT count(*) FROM orders')).scalar_one()==0
        assert db.execute(text('SELECT count(*) FROM buyers')).scalar_one()==0
    b=buyer(c);order=create(c,b,[line(p)])
    result=run([sys.executable,'-m','alembic','downgrade','c24a9b71e603'],capture_output=True,text=True)
    assert result.returncode!=0 and 'Cannot discard' in result.stderr
    assert c.get('/api/v1/orders/'+order['id']).status_code==200


@pytest.mark.parametrize('operation',['reserve','sell'])
def test_competing_orders_cannot_allocate_same_last_units(setup,operation):
    from threading import Barrier
    c,b,p=setup;one=create(c,b,[line(p,3)]);two=create(c,b,[line(p,3)]);barrier=Barrier(2)
    def send(order):
        with TestClient(app) as other:
            other.cookies.update(dict(c.cookies));other.headers.update(dict(c.headers));barrier.wait(timeout=5)
            return action(other,order,operation).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(send,[one,two]))
    assert sorted(codes)==[200,409]
    assert state(c,p)['quantity']==(0 if operation=='sell' else 3)
    assert state(c,p)['reserved_quantity']==(3 if operation=='reserve' else 0)


def test_cancel_racing_reserved_sale_is_atomic(setup):
    from threading import Barrier
    c,b,p=setup;order=create(c,b,[line(p)]);assert action(c,order,'reserve').status_code==200
    barrier=Barrier(2)
    def send(kind):
        with TestClient(app) as other:
            other.cookies.update(dict(c.cookies));other.headers.update(dict(c.headers));barrier.wait(timeout=5)
            return action(other,order,kind).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(send,['sell','cancel']))
    assert sorted(codes)==[200,409]
    current=c.get('/api/v1/orders/'+order['id']).json()
    assert state(c,p)['reserved_quantity']==0
    assert state(c,p)['quantity']==(2 if current['sold_at'] else 3)
    assert bool(current['sold_at']) != (current['status']=='cancelled')


def test_concurrent_creation_numbers_and_idempotency_keys(setup):
    from threading import Barrier
    c,b,p=setup;payload={'buyer_id':b['id'],'lines':[line(p)],**key()};barrier=Barrier(2)
    def send(body):
        with TestClient(app) as other:
            other.cookies.update(dict(c.cookies));other.headers.update(dict(c.headers));barrier.wait(timeout=5)
            r=other.post('/api/v1/orders',json=body);assert r.status_code==201,r.text;return r.json()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,[payload,payload]))
    assert results[0]==results[1]
    barrier=Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,[{**payload,**key()},{**payload,**key()}]))
    assert sorted(r['number'] for r in results)==[2,3]
    assert c.get('/api/v1/orders',params={'limit':1,'offset':1}).json()['total']==3


def test_large_decimal_totals_and_status_replay_no_financial_guessing(setup):
    c,b,p=setup;order=create(c,b,[line(p,1000000,unit_price='999999999999.99',currency='USD')])
    assert order['totals_by_currency']=={'USD':'999999999999990000.00'}
    assert order['lines'][0]['line_total']=='999999999999990000.00'
    # A draft may exceed stock, but its reserve/sale can never succeed.
    assert action(c,order,'reserve').status_code==409
    assert action(c,order,'sell').status_code==409
    assert state(c,p)['quantity']==3
    assert c.patch('/api/v1/orders/'+order['id'],json={**key(),'city':None}).status_code==422


def test_order_lifecycle_keeps_unknown_contacts_and_other_accounts_separate(setup):
    c,b,p=setup;order=create(c,b,[line(p)])
    original_phone=order['contact_phone']
    assert c.put('/api/v1/buyers/'+b['id'],json={'name':'New buyer name','phone':'0677778899'}).status_code==200
    assert c.get('/api/v1/orders/'+order['id']).json()['contact_phone']==original_phone
    assert c.get('/api/v1/orders',params={'phone':'0677778899'}).json()['total']==1
    assert action(c,order,'reserve').status_code==200
    body={**key(),'status':'shipped'}
    first=action(c,order,'status',body);assert first.status_code==200
    assert action(c,order,'status',body).json()==first.json()
    assert action(c,order,'status',{**body,'status':'completed'}).status_code==409
    assert action(c,order,'cancel').status_code==200
    assert state(c,p)['quantity']==3 and state(c,p)['reserved_quantity']==0


def test_draft_with_archived_part_can_still_be_cancelled(setup):
    c,b,p=setup;order=create(c,b,[line(p)])
    assert c.post('/api/v1/archive/parts/'+p['id']).status_code==200
    assert action(c,order,'cancel').json()['status']=='cancelled'


def test_cross_donor_prices_actor_and_full_mid_operation_rollback(setup,vehicle,monkeypatch):
    from app.services import orders as domain
    from fastapi import HTTPException
    c,b,p=setup
    second_vehicle=c.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2018}).json()
    second=stocked(c,second_vehicle,quantity=3,name='R4 second donor',oem_number='R4-OEM')
    before=[state(c,x) for x in (p,second)]
    order=create(c,b,[line(p,2,unit_price='12.34'),line(second,unit_price='0',currency='USD')])
    url='/api/v1/orders/'+order['id']
    detail=c.get(url).json()
    assert len({x['donor_snapshot']['id'] for x in detail['lines']})==2
    assert next(x for x in detail['lines'] if x['part_id']==second['id'])['current_part']=={'oem_number':'R4-OEM','available_quantity':3}
    assert [state(c,x) for x in (p,second)]==before
    c.patch('/api/v1/parts/'+p['id']+'/price',json={'selling_price':'987.65','currency':'USD'})
    original=domain.stock;calls=[]
    def fail_second(*args,**kwargs):
        calls.append(args[1].id)
        if len(calls)==2:raise HTTPException(409,'R4 simulated failure after first write')
        return original(*args,**kwargs)
    body=key()
    with monkeypatch.context() as patch:
        patch.setattr(domain,'stock',fail_second)
        assert action(c,order,'sell',body).status_code==409
    assert len(calls)==2
    assert [state(c,x)['quantity'] for x in (p,second)]==[3,3]
    assert c.get(url).json()['sold_at'] is None
    assert c.get('/api/v1/audit',params={'type':'sale'}).json()['total']==0
    sold=action(c,order,'sell',body)
    assert sold.status_code==200,sold.text
    assert sold.json()['totals_by_currency']=={'UAH':'24.68','USD':'0.00'}
    assert action(c,order,'sell',body).json()==sold.json()
    assert action(c,order,'sell').status_code==409
    assert c.put(url+'/lines',json={**key(),'lines':[line(p)]}).status_code==409
    events=c.get(url+'/events').json()['items']
    created=next(e for e in events if e['type']=='created')
    confirmed=next(e for e in events if e['type']=='sale_confirmed')
    assert created['actor_id']==confirmed['actor_id']==c.get('/api/v1/auth/me').json()['id']
    assert c.get('/api/v1/audit',params={'type':'sale'}).json()['total']==2


def test_current_inventory_is_permission_scoped_and_actor_is_not_assignable(setup):
    from sqlalchemy.orm import Session
    from app.models import Account
    from app.services.auth import hasher
    c,b,p=setup;order=create(c,b,[line(p)])
    owner=c.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        reader=Account(email='r4-contact-reader@example.test',name='R4 contact reader',password_hash=hasher.hash('local-reader-password'),role='MANAGER',workspace_account_id=owner,permissions=['orders.view'])
        db.add(reader);db.commit()
    with TestClient(app) as reader:
        r=reader.post('/api/v1/auth/login',json={'email':'r4-contact-reader@example.test','password':'local-reader-password'});reader.headers['X-CSRF-Token']=r.json()['csrf_token']
        row=reader.get('/api/v1/orders/'+order['id']).json()
        assert 'current_part' not in row['lines'][0] and 'unit_price' not in row['lines'][0]
        assert action(reader,order,'sell').status_code==403
        assert reader.put('/api/v1/orders/'+order['id']+'/lines',json={**key(),'lines':[line(p)]}).status_code==403
    for extra in ({'actor_id':'other-actor'},{'manager_id':'other-actor'}):
        r=c.post('/api/v1/orders',json={**key(),'buyer_id':b['id'],'lines':[line(p)],**extra})
        assert r.status_code==422,r.text
    assert c.post('/api/v1/orders',json={**key(),'buyer_id':b['id'],'lines':[{'part_id':p['id'],'quantity':1,'currency':'UAH'}]}).status_code==422
