from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from app.models import Account,Operation,OrderEvent
from app.services.auth import hasher
from conftest import signup
from test_orders import buyer,stocked,line,create,action


def test_mixed_journal_phone_actor_and_explicit_links(logged,vehicle):
    p=stocked(logged,vehicle,quantity=4);b=buyer(logged);o=create(logged,b,[line(p,quantity=2,unit_price='12.34',currency='USD')]);assert action(logged,o,'sell').status_code==200
    owner=logged.get('/api/v1/auth/me').json()['id'];r=logged.get('/api/v1/sales-center').json();assert r['total']==2
    assert {i['kind'] for i in r['items']}=={'order','sale'};sale=next(i for i in r['items'] if i['kind']=='sale');order=next(i for i in r['items'] if i['kind']=='order')
    assert sale['order_id']==o['id'] and order['id']==o['id'] and sale['manager_id']==owner
    assert sale['totals_by_currency']=={'USD':'24.68'} and order['position_count']==1
    assert logged.get('/api/v1/sales-center?kind=sales&phone=0501234567').json()['total']==1
    assert logged.get('/api/v1/sales-center?kind=orders&phone=%2B380501234567').json()['total']==1
    assert logged.get('/api/v1/sales-center?manager_id='+owner).json()['total']==2
    assert logged.get('/api/v1/sales-center?number='+str(o['number'])).json()['total']==2
    assert logged.get('/api/v1/sales-center?vehicle_id='+vehicle['id']).json()['total']==2
    assert logged.get('/api/v1/sales-center?status=sold').json()['total']==2
    assert logged.get('/api/v1/sales-center?status=new').json()['total']==1
    assert logged.get('/api/v1/sales-center?date_from=2100-01-01T00:00:00Z').json()['total']==0
    first=logged.get('/api/v1/sales-center?limit=1').json();second=logged.get('/api/v1/sales-center?limit=1&offset=1').json();assert first['total']==2 and first['items'][0]['kind']!=second['items'][0]['kind']
    assert logged.get('/api/v1/sales-center?phone=xx').status_code==422
    assert logged.get('/api/v1/sales-center?date_from=2026-10-22&date_to=2026-10-20').status_code==422


def test_inactive_and_renamed_actor_uses_historic_identity(logged,vehicle):
    p=stocked(logged,vehicle,quantity=2);b=buyer(logged);o=create(logged,b,[line(p)]);assert action(logged,o,'sell').status_code==200
    owner=logged.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:a=db.get(Account,owner);a.name='Новий поточний підпис';db.commit()
    rows=logged.get('/api/v1/sales-center').json()['items'];assert all(r['manager_name']=='Власник' for r in rows)
    summary=logged.get('/api/v1/sales/summary?date_from=2020-01-01&date_to=2020-01-31&manager_id='+owner);assert summary.status_code==200


def test_sales_only_cannot_read_or_filter_phone_or_orders(logged,vehicle):
    p=stocked(logged,vehicle,quantity=2);b=buyer(logged);o=create(logged,b,[line(p)]);assert action(logged,o,'sell').status_code==200
    owner=logged.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        for kind,permissions in [('reader',['sales.view']),('orders',['orders.view']),('blocked',[])]:db.add(Account(email=kind+'@example.test',name=kind,password_hash=hasher.hash('local-reader-password'),role='MANAGER',workspace_account_id=owner,permissions=permissions))
        db.commit()
    for kind in ['reader','orders','blocked']:
        with TestClient(app) as c:
            assert c.post('/api/v1/auth/login',json={'email':kind+'@example.test','password':'local-reader-password'}).status_code==200
            r=c.get('/api/v1/sales-center')
            if kind=='blocked':assert r.status_code==403;continue
            rows=r.json()['items'];assert len(rows)==1;assert rows[0]['kind']==('sale' if kind=='reader' else 'order')
            assert 'totals_by_currency' not in rows[0]
            if kind=='reader':assert not rows[0]['contact_phone'] and not rows[0]['buyer_phone'];assert c.get('/api/v1/sales-center?phone=123').status_code==403
    with TestClient(app) as other:
        signup(other,'foreign@example.test');assert other.get('/api/v1/sales-center').json()['total']==0
        assert other.get('/api/v1/sales-center?manager_id='+owner).json()['total']==0


def test_inactive_employee_is_not_replaced_by_current_owner(logged,vehicle):
    from uuid import uuid4
    p=stocked(logged,vehicle,quantity=2);owner=logged.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        worker=Account(email='inactive@example.test',name='Історичний менеджер',password_hash=hasher.hash('local-reader-password'),role='MANAGER',workspace_account_id=owner,permissions=['sales.create']);db.add(worker);db.commit();wid=worker.id
    with TestClient(app) as c:
        r=c.post('/api/v1/auth/login',json={'email':'inactive@example.test','password':'local-reader-password'});c.headers['X-CSRF-Token']=r.json()['csrf_token']
        assert c.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'sale','quantity':1,'sale_price':'7.50','sale_currency':'USD','request_key':str(uuid4())}).status_code==200
    with Session(engine()) as db:a=db.get(Account,wid);a.is_active=False;a.name='Змінене ім’я';db.commit()
    r=logged.get('/api/v1/sales-center?manager_id='+wid).json();assert r['total']==1 and r['items'][0]['manager_name']=='Історичний менеджер'
    assert next(m for m in logged.get('/api/v1/sales-center/managers').json()['items'] if m['id']==wid)['active'] is False
