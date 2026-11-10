"""Disposable PostgreSQL only: synthetic physical assemblies, never live data."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from app.db import engine
from app.main import app
from app.models import AssemblyMembership,DismantlingItem,Part,Operation,OrderLine,Vehicle
from app.services import assemblies
from conftest import signup


def key():return str(uuid4())

@pytest.fixture(autouse=True)
def feature(monkeypatch):monkeypatch.setenv('ASSEMBLY_INVENTORY_ENABLED','true')

@pytest.fixture
def group(logged,vehicle):
    with Session(engine()) as db:
        account=db.get(Vehicle,vehicle['id']).account_id;nodes=[];parts=[]
        for i in range(13):
            p=Part(account_id=account,vehicle_id=vehicle['id'],name='Двері в зборі' if i==0 else f'Компонент {i}',quantity=1,reserved_quantity=0,individually_tracked=True)
            db.add(p);db.flush()
            n=DismantlingItem(account_id=account,vehicle_id=vehicle['id'],part_id=p.id,source='assembly.synthetic',catalog_key=str(i),category_key='body',category_name='Кузов',subcategory_key='door',subcategory_name='Двері',name=p.name,quantity=1)
            db.add(n);db.flush();nodes.append(n.id);parts.append(p.id)
        db.commit()
    return dict(vehicle=vehicle['id'],account=account,nodes=nodes,parts=parts)

def change(c,g,action,**fields):return c.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=dict(request_key=key(),action=action,confirm_physical=True,**fields))
def preview(c,g,node=0):
    r=c.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies/{g['nodes'][node]}/preview");assert r.status_code==200,r.text
    return r.json()
def attach_all(c,g):
    for child in g['nodes'][1:]:
        r=change(c,g,'attach',parent_id=g['nodes'][0],item_id=child);assert r.status_code==200,r.text
    r=change(c,g,'confirm',item_id=g['nodes'][0],token=preview(c,g)['token']);assert r.status_code==200,r.text

def sell(c,g,part=0,**extra):
    data=dict(type='sale',quantity=1,request_key=key(),sale_price='500.00',sale_currency='UAH')
    if part==0:data['assembly_token']=preview(c,g)['token']
    return c.post('/api/v1/parts/'+g['parts'][part]+'/operations',json={**data,**extra})

def test_whole_12_children_single_revenue_replay_and_return(logged,group,monkeypatch):
    g=group;attach_all(logged,g);request=key();token=preview(logged,g)['token']
    r=sell(logged,g,request_key=request,assembly_token=token);assert r.status_code==200,r.text
    assert sell(logged,g,request_key=request,assembly_token=token).json()==r.json()
    assert sell(logged,g,request_key=request,assembly_token=token,sale_price='501').status_code==409
    with Session(engine()) as db:
        ops=list(db.scalars(select(Operation).where(Operation.type=='sale')))
        assert len(ops)==1 and ops[0].after['sale']['total']=='500.00';sale_id=ops[0].id
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='assembly_included_sale'))==12
        assert all(p.quantity==0 for p in db.scalars(select(Part)))
        assert len(list(db.scalars(select(DismantlingItem))))==13
    context=logged.get('/api/v1/parts/'+g['parts'][1]).json()['assembly_context']
    assert context['state']=='sold_in_assembly' and context['parent_name']=='Двері в зборі'
    monkeypatch.setenv('ASSEMBLY_INVENTORY_ENABLED','false');assert sell(logged,g,part=1).status_code==409
    monkeypatch.setenv('ASSEMBLY_INVENTORY_ENABLED','true')
    ret=dict(request_key=key(),action='return',sale_operation_id=sale_id,confirm_inventory_return_only=True)
    url=f"/api/v1/vehicles/{g['vehicle']}/assemblies"
    assert logged.post(url,json=ret).status_code==200
    assert logged.get('/api/v1/parts/'+g['parts'][1]).json()['assembly_context']['state']=='contained'
    assert logged.post(url,json=ret).status_code==200
    assert logged.post(url,json={**ret,'request_key':key()}).status_code==409
    with Session(engine()) as db:
        assert db.get(Part,g['parts'][0]).quantity==1
        assert all(db.get(Part,id).quantity==0 for id in g['parts'][1:])
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='sale'))==1

def test_detach_sell_remainder(logged,group):
    g=group;attach_all(logged,g)
    assert change(logged,g,'detach',item_id=g['nodes'][1]).status_code==200
    assert sell(logged,g,part=1).status_code==200
    assert sell(logged,g).status_code==409
    r=sell(logged,g,assembly_remainder=True,assembly_description='Двері без склопідіймача');assert r.status_code==200,r.text
    with Session(engine()) as db:
        assert db.get(DismantlingItem,g['nodes'][1]).assembly_consumed_operation_id is None
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='sale'))==2
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='assembly_included_sale'))==11

def test_nested_engine_detached_generator(logged,group):
    g=group
    for parent,child in [(0,1),(1,2),(0,3)]:
        assert change(logged,g,'attach',parent_id=g['nodes'][parent],item_id=g['nodes'][child]).status_code==200
    assert change(logged,g,'detach',item_id=g['nodes'][3]).status_code==200
    assert change(logged,g,'confirm',item_id=g['nodes'][0],token=preview(logged,g)['token']).status_code==200
    assert sell(logged,g).status_code==200
    with Session(engine()) as db:
        assert db.get(Part,g['parts'][3]).quantity==1
        assert db.get(DismantlingItem,g['nodes'][2]).assembly_consumed_operation_id
        assert not db.get(DismantlingItem,g['nodes'][3]).assembly_consumed_operation_id

def test_orders_reserve_release_conflicting_lines(logged,group):
    g=group;attach_all(logged,g)
    buyer=logged.post('/api/v1/buyers',json={'name':'Synthetic','phone':'0501234567'}).json()
    line=dict(part_id=g['parts'][0],quantity=1,unit_price='321.00',currency='USD',assembly_token=preview(logged,g)['token'])
    assert logged.post('/api/v1/orders',json=dict(request_key=key(),buyer_id=buyer['id'],lines=[line,{**line,'part_id':g['parts'][1]}])).status_code==409
    r=logged.post('/api/v1/orders',json=dict(request_key=key(),buyer_id=buyer['id'],lines=[line]));assert r.status_code==201,r.text
    url='/api/v1/orders/'+r.json()['id']
    assert logged.post(url+'/reserve',json={'request_key':key()}).status_code==200
    assert sell(logged,g).status_code==409
    assert change(logged,g,'detach',item_id=g['nodes'][1]).status_code==409
    assert sell(logged,g,part=1).status_code==409
    assert logged.post(url+'/release',json={'request_key':key()}).status_code==200
    assert logged.post(url+'/reserve',json={'request_key':key()}).status_code==200
    r=logged.post(url+'/sell',json={'request_key':key()});assert r.status_code==200,r.text
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(OrderLine))==1
        sale=db.scalar(select(Operation).where(Operation.type=='sale'))
        assert sale.after['sale']['currency']=='USD' and sale.after['sale']['total']=='321.00'

def test_component_reserve_and_receipt_bypass(logged,group):
    g=group;url='/api/v1/parts/'+g['parts'][1]+'/operations'
    assert logged.post(url,json=dict(type='reserve',quantity=1,reason='Manual reserve')).status_code==200
    assert change(logged,g,'attach',parent_id=g['nodes'][0],item_id=g['nodes'][1]).status_code==409
    assert logged.post(url,json=dict(type='release',quantity=1,reason='Manual release')).status_code==200
    assert change(logged,g,'attach',parent_id=g['nodes'][0],item_id=g['nodes'][1]).status_code==200
    for kind in ('receipt','correction','write_off','reserve'):
        assert logged.post(url,json=dict(type=kind,quantity=1,reason='Must not bypass containment')).status_code==409

def test_cycles_scope_second_parent_and_sql_guard(logged,group):
    g=group
    assert change(logged,g,'attach',parent_id=g['nodes'][0],item_id=g['nodes'][1]).status_code==200
    assert change(logged,g,'attach',parent_id=g['nodes'][2],item_id=g['nodes'][1]).status_code==409
    assert change(logged,g,'attach',parent_id=g['nodes'][1],item_id=g['nodes'][0]).status_code==409
    with Session(engine()) as db:
        edge=db.scalar(select(AssemblyMembership));db.add(AssemblyMembership(account_id=g['account'],vehicle_id=g['vehicle'],parent_item_id=g['nodes'][1],child_item_id=g['nodes'][0],attached_operation_id=edge.attached_operation_id))
        with pytest.raises(DBAPIError):db.commit()
    with TestClient(app) as other:
        signup(other,'other-assembly@example.test')
        assert other.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies").status_code==404
        assert change(other,g,'attach',parent_id=g['nodes'][0],item_id=g['nodes'][2]).status_code==404

def test_concurrent_root_child_sale(logged,group):
    g=group;attach_all(logged,g);token=preview(logged,g)['token'];cookies=dict(logged.cookies);headers=dict(logged.headers)
    def request(index):
        with TestClient(app) as c:
            c.cookies.update(cookies);c.headers.update(headers)
            return sell(c,g,part=index,**({'assembly_token':token} if index==0 else {})).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(request,[0,1]))
    assert sorted(results)==[200,409]
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='sale'))==1

def test_last_child_error_rolls_back_entire_sale(logged,group,monkeypatch):
    g=group;attach_all(logged,g);original=assemblies.record;count=0
    def broken(*args,**kwargs):
        nonlocal count
        if args[3]=='assembly_included_sale':
            count+=1
            if count==12:raise HTTPException(409,'Synthetic final-component failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(assemblies,'record',broken)
    assert sell(logged,g).status_code==409
    with Session(engine()) as db:
        assert db.get(Part,g['parts'][0]).quantity==1
        assert not db.scalar(select(Operation.id).where(Operation.type=='sale'))
        assert all(n.assembly_consumed_operation_id is None for n in db.scalars(select(DismantlingItem)))


def test_feature_gate_stale_preview_and_unstocked_component(logged,group,monkeypatch):
    g=group;monkeypatch.setenv('ASSEMBLY_INVENTORY_ENABLED','false')
    assert logged.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies/readiness").json()=={'enabled':False}
    assert logged.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies").status_code==404
    monkeypatch.setenv('ASSEMBLY_INVENTORY_ENABLED','true')
    with Session(engine()) as db:
        n=DismantlingItem(account_id=g['account'],vehicle_id=g['vehicle'],name='Confirmed unstocked component',source='synthetic',catalog_key='unstocked',category_key='body',category_name='Body',subcategory_key='door',subcategory_name='Door',quantity=1)
        db.add(n);db.flush();id=n.id;db.commit()
    assert change(logged,g,'attach',parent_id=g['nodes'][0],item_id=id).status_code==200
    stale=preview(logged,g)['token']
    assert change(logged,g,'attach',parent_id=g['nodes'][0],item_id=g['nodes'][1]).status_code==200
    assert sell(logged,g,assembly_token=stale,assembly_remainder=True,assembly_description='Actual remainder').status_code==409
    # The common dismantling receipt service cannot create a second standalone part.
    from app.services.dismantling import receipt
    from types import SimpleNamespace
    with Session(engine()) as db:
        with pytest.raises(HTTPException):receipt(db,db.get(DismantlingItem,id),SimpleNamespace(),g['account'])
    r=change(logged,g,'detach',item_id=id);assert r.status_code==200,r.text
    with Session(engine()) as db:assert db.get(Part,r.json()['part_id']).quantity==1


def test_cross_donor_and_manager_write_permissions(logged,group,monkeypatch):
    g=group
    second=logged.post('/api/v1/vehicles',json={'manufacturer':'Synthetic','model':'Other donor','year':2019}).json()
    with Session(engine()) as db:
        n=DismantlingItem(account_id=g['account'],vehicle_id=second['id'],name='Other donor component',source='synthetic',catalog_key='x',category_key='body',category_name='Body',subcategory_key='door',subcategory_name='Door')
        db.add(n);db.flush();id=n.id;db.commit()
    assert change(logged,g,'attach',parent_id=g['nodes'][0],item_id=id).status_code==404
    from test_team import employee,activate
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    _,credentials=employee(logged,permissions=['vehicles.view','inventory.view'])
    manager=activate(credentials)
    try:
        assert manager.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies").status_code==200
        assert change(manager,g,'attach',parent_id=g['nodes'][0],item_id=g['nodes'][1]).status_code==403
    finally:manager.close()


def test_552_potential_positions_have_no_automatic_stock(logged,group):
    g=group
    with Session(engine()) as db:
        for i in range(539):db.add(DismantlingItem(account_id=g['account'],vehicle_id=g['vehicle'],name=f'Potential {i}',source='potential.synthetic',catalog_key=str(i),category_key='body',category_name='Body',subcategory_key='door',subcategory_name='Door'))
        db.commit()
    r=logged.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies");assert r.status_code==200
    assert len(r.json()['items'])==552 and r.json()['counts']['potential']==552
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==13


def test_template_version_and_explicit_single_root_receipt(logged,group):
    g=group
    from app.models.canonical import CanonicalType,CanonicalPlacement
    with Session(engine()) as db:
        for i in (1,2):
            db.add(CanonicalType(id=f'template-type-{i}',identity_key=f'template-type-{i}',name=f'Synthetic type {i}',category='Body',subcategory='Door',provenance={}))
            db.flush();db.add(CanonicalPlacement(id=f'template-placement-{i}',type_id=f'template-type-{i}',identity_key=f'template-position-{i}',details={},side='left',position='front'))
        n=DismantlingItem(account_id=g['account'],vehicle_id=g['vehicle'],name='Potential physical root',source='manual.synthetic',catalog_key='receipt-root',category_key='body',category_name='Body',subcategory_key='door',subcategory_name='Door')
        db.add(n);db.flush();node=n.id;db.commit()
    url=f"/api/v1/vehicles/{g['vehicle']}/assemblies/templates"
    body=dict(request_key=key(),name='Synthetic configurable door',version=1,provenance='Synthetic test only',template={'placements':['template-placement-1','template-placement-2'],'edges':[{'parent':'template-placement-1','child':'template-placement-2','optional':True,'quantity':1}]})
    first=logged.post(url,json=body);assert first.status_code==200,first.text
    assert logged.post(url,json=body).json()==first.json()
    assert logged.post(url,json={**body,'request_key':key(),'provenance':'Changed same version'}).status_code==409
    cyclic={**body,'request_key':key(),'version':2,'template':{**body['template'],'edges':body['template']['edges']+[{'parent':'template-placement-2','child':'template-placement-1'}]}}
    assert logged.post(url,json=cyclic).status_code==422
    result=change(logged,g,'receipt',item_id=node);assert result.status_code==200,result.text
    assert change(logged,g,'receipt',item_id=node).status_code==409
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==14
        assert db.get(Part,result.json()['part_id']).quantity==1


def test_component_cost_does_not_silently_disappear(logged,group):
    g=group
    with Session(engine()) as db:db.get(Part,g['parts'][1]).unit_cost=25;db.commit()
    r=change(logged,g,'attach',parent_id=g['nodes'][0],item_id=g['nodes'][1])
    assert r.status_code==409 and 'собівартість' in r.text
    with Session(engine()) as db:
        assert db.get(Part,g['parts'][1]).quantity==1
        assert not db.scalar(select(AssemblyMembership.id))


def test_physical_identity_cannot_be_unlinked_or_moved_with_sql(logged,group):
    from sqlalchemy import text
    g=group
    assert change(logged,g,'attach',parent_id=g['nodes'][0],item_id=g['nodes'][1]).status_code==200
    with Session(engine()) as db:
        with pytest.raises(DBAPIError):
            db.execute(text('UPDATE dismantling_items SET part_id=NULL WHERE id=:id'),{'id':g['nodes'][1]});db.commit()
    with Session(engine()) as db:
        with pytest.raises(DBAPIError):
            db.execute(text('UPDATE parts SET vehicle_id=NULL WHERE id=:id'),{'id':g['parts'][1]});db.commit()
    with Session(engine()) as db:
        with pytest.raises(DBAPIError):db.execute(text('DELETE FROM assembly_memberships'));db.commit()


def test_explicit_legacy_part_link_preserves_quantity_and_photos_identity(logged,group):
    g=group
    p=logged.post('/api/v1/parts',json={'name':'Existing Plan.Parts/manual position','vehicle_id':g['vehicle']}).json()
    assert logged.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'receipt','quantity':1,'reason':'Synthetic legacy stock'}).status_code==200
    body=dict(action='link_part',part_id=p['id'],confirm_physical=True,request_key=key())
    url=f"/api/v1/vehicles/{g['vehicle']}/assemblies"
    r=logged.post(url,json=body);assert r.status_code==200,r.text
    assert logged.post(url,json=body).json()==r.json()
    assert logged.post(url,json={**body,'request_key':key()}).json()['created'] is False
    with Session(engine()) as db:
        assert db.get(Part,p['id']).quantity==1
        assert db.get(DismantlingItem,r.json()['item_id']).part_id==p['id']
        assert db.scalar(select(func.count()).select_from(Part))==14


def test_legacy_order_request_fingerprint_replays_after_schema_extension(logged,group):
    import hashlib,json
    from app.models import OrderRequest,Order
    from app.schemas.orders import CreateOrder
    g=group
    buyer=logged.post('/api/v1/buyers',json={'name':'Legacy replay fixture','phone':'0501234567'}).json()
    body=dict(request_key=key(),buyer_id=buyer['id'],lines=[dict(part_id=g['parts'][0],quantity=1,unit_price='12.00',currency='UAH')])
    payload=CreateOrder.model_validate(body).model_dump(mode='json',exclude={'request_key'})
    for line in payload['lines']:
        for field in ('assembly_token','assembly_description','assembly_remainder'):line.pop(field)
    fingerprint=hashlib.sha256(json.dumps({'scope':'orders:create','data':payload},sort_keys=True).encode()).hexdigest()
    with Session(engine()) as db:
        db.add(OrderRequest(account_id=g['account'],actor_id=g['account'],request_key=body['request_key'],fingerprint=fingerprint,response={'legacy_result':'unchanged'}));db.commit()
    r=logged.post('/api/v1/orders',json=body);assert r.status_code==201 and r.json()=={'legacy_result':'unchanged'}
    changed={**body,'lines':[{**body['lines'][0],'unit_price':'13.00'}]}
    assert logged.post('/api/v1/orders',json=changed).status_code==409
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Order))==0
