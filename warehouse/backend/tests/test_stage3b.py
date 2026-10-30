"""Virtual stock acceptance; isolated local PostgreSQL only, no live publish."""
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
import pytest
from app.db import engine
from app.main import app
from app.models import Part,Operation,DismantlingItem,Vehicle
from app.services import virtual_inventory as virtual
from test_stage2d import fixture_catalogue,candidate
from test_v3_release_audit import all_tables


def path(v):return f"/api/v1/vehicles/{v['id']}/virtual-dismantling"
def read(c,v):
    r=c.get(path(v));assert r.status_code==200,r.text;return r.json()
def payload(c,v,**kw):return dict(facts=[],confirm=True,etag=read(c,v)['etag'],request_key=str(uuid4()),**kw)
def activate(c,v,data=None):return c.post(path(v)+'/activate',json=data or payload(c,v))
def available(c,v,ids,enabled):return c.post(path(v)+'/availability',json=dict(ids=ids,enabled=enabled,etag=read(c,v)['etag'],request_key=str(uuid4())))
def operation(c,p,type,quantity,**kw):return c.post(f'/api/v1/parts/{p}/operations',json=dict(type=type,quantity=quantity,reason='Local virtual inventory test',request_key=str(uuid4()),**kw))

def test_activation_pending_replay_and_single_ledger(client,vehicle,monkeypatch):
    tid=candidate('Ambiguous')['canonical_part_type_id']
    fixture_catalogue(monkeypatch,[candidate('Safe'),candidate('Ambiguous',tid),candidate('Ambiguous left',tid,side='left')])
    data=payload(client,vehicle);r=activate(client,vehicle,data);assert r.status_code==200,r.text
    assert r.json()['activated']==1 and r.json()['pending']==2
    state=read(client,vehicle);assert state['virtual_mode']
    row=state['items'][0];p=client.get('/api/v1/parts/'+row['part_id']).json()
    assert p['quantity']==1 and p['condition']=='unknown' and p['selling_price'] is None and p['unit_cost'] is None
    assert p['physical_location_kind']=='on_vehicle' and p['quantity_basis']=='assumed'
    assert p['availability']=='unchecked'  # Virtual quantity is not physical inspection evidence.
    assert client.get('/api/v1/inventory?in_stock=true').json()['total']==1
    assert activate(client,vehicle,data).json()==r.json()
    assert activate(client,vehicle).json()['activated']==0
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==1
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='virtual_activation'))==1
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==0
        item=db.get(DismantlingItem,row['id']);assert item.received_at is None and item.status=='unchecked'
    legacy=client.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/actions",json=dict(ids=[row['id']],action='receipt',quantity=1))
    assert legacy.status_code!=200


def test_availability_reserve_sale_and_refresh(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Safe')]);assert activate(client,vehicle).status_code==200
    row=read(client,vehicle)['items'][0];p=row['part_id']
    assert available(client,vehicle,[row['id']],False).status_code==200
    assert client.get('/api/v1/inventory?in_stock=true').json()['total']==0
    assert operation(client,p,'sale',1).status_code==409
    assert operation(client,p,'reserve',1).status_code==409
    assert available(client,vehicle,[row['id']],True).status_code==200
    assert operation(client,p,'reserve',1).status_code==200
    assert available(client,vehicle,[row['id']],False).status_code==409
    assert activate(client,vehicle).json()['activated']==0
    assert read(client,vehicle)['items'][0]['stock']['state']=='reserved'
    assert operation(client,p,'sale',1).status_code==409
    assert operation(client,p,'release',1).status_code==200
    assert operation(client,p,'sale',1,sale_price='25.00',sale_currency='UAH').status_code==200
    assert activate(client,vehicle).json()['activated']==0
    assert read(client,vehicle)['items'][0]['stock']['state']=='sold'
    assert available(client,vehicle,[row['id']],True).status_code==409
    assert client.get('/api/v1/parts/'+p).json()['quantity']==0


def test_partial_sales_zero_correction_and_location(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Safe')]);activate(client,vehicle)
    p=read(client,vehicle)['items'][0]['part_id']
    assert operation(client,p,'correction',5).status_code==200
    assert operation(client,p,'reserve',2).status_code==200
    assert operation(client,p,'sale',2).status_code==200
    s=read(client,vehicle)['items'][0]['stock'];assert (s['quantity'],s['reserved_quantity'],s['available_quantity'],s['sold_quantity'])==(3,2,1,2)
    assert operation(client,p,'correction',1).status_code==409
    assert operation(client,p,'transfer',0,location='Shelf A',physical_location_kind='on_shelf').status_code==200
    assert read(client,vehicle)['items'][0]['stock']['physical_location_kind']=='on_shelf'
    assert operation(client,p,'release',2).status_code==200
    assert operation(client,p,'write_off',3).status_code==200
    assert read(client,vehicle)['items'][0]['stock']['state'] is None
    # No sale on a fresh second part: write-off is not sold.
    fixture_catalogue(monkeypatch,[candidate('Safe'),candidate('Another')]);activate(client,vehicle)
    p2=next(i for i in read(client,vehicle)['items'] if i['name']=='Another')['part_id']
    assert operation(client,p2,'write_off',1).status_code==200
    assert next(i for i in read(client,vehicle)['items'] if i['part_id']==p2)['stock']['state'] is None


def test_base_template_no_published_catalogue_and_no_get_writes(client,vehicle):
    with Session(engine()) as db:before=all_tables(db)
    read(client,vehicle)
    with Session(engine()) as db:assert all_tables(db)==before
    r=activate(client,vehicle);assert r.status_code==200,r.text
    assert r.json()['activated']>0 and r.json()['basic_coverage']
    assert read(client,vehicle)['basic_coverage']


def test_engine_refresh_preserves_price_exclusions_and_history(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,lambda config:[candidate('Common')]+([candidate('Diesel')] if config['values'].get('powertrain')=='diesel' else []))
    activate(client,vehicle);row=read(client,vehicle)['items'][0];p=row['part_id']
    assert client.patch('/api/v1/parts/'+p+'/price',json=dict(selling_price='42.00',currency='USD')).status_code==200
    available(client,vehicle,[row['id']],False)
    r=activate(client,vehicle,{**payload(client,vehicle),'facts':[dict(field='powertrain',value='diesel',kind='manual',reference='Local owner',confidence='reported')]})
    assert r.status_code==200,r.text
    state=read(client,vehicle);assert r.json()['activated']==1
    original=next(i for i in state['items'] if i['part_id']==p)
    assert not original['included'] and original['stock']['selling_price']=='42.00' and original['stock']['currency']=='USD'


def test_atomic_failure_after_first_activation(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('A'),candidate('B')])
    with Session(engine()) as db:before=all_tables(db)
    original=virtual.stock;calls=[]
    def fail(*args,**kwargs):
        value=original(*args,**kwargs);calls.append(1)
        if len(calls)==2:raise RuntimeError('Injected failure after stock writes')
        return value
    monkeypatch.setattr(virtual,'stock',fail)
    with pytest.raises(RuntimeError):activate(client,vehicle)
    with Session(engine()) as db:assert all_tables(db)==before


def test_concurrent_commands_no_duplicates(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Safe')]);data=payload(client,vehicle)
    def send(_):
        with TestClient(app) as c:
            c.cookies.update(client.cookies);c.headers['X-CSRF-Token']=client.headers['X-CSRF-Token'];r=activate(c,vehicle,data);return r.status_code,r.json()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,range(2)))
    assert [r[0] for r in results]==[200,200] and results[0][1]==results[1][1]
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==1
    assert activate(client,vehicle,{**data,'request_key':str(uuid4())}).status_code==409


def test_archive_and_forged_ids_fail_closed(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Safe')]);activate(client,vehicle)
    row=read(client,vehicle)['items'][0]
    assert available(client,vehicle,['not-own'],False).status_code==404
    csrf=client.headers.pop('X-CSRF-Token');assert activate(client,vehicle).status_code==403;client.headers['X-CSRF-Token']=csrf
    assert client.post('/api/v1/archive/parts/'+row['part_id'],json={'reason':'Local archive test'}).status_code in (200,422)
    # Direct local fixture archive removes API-schema uncertainty.
    with Session(engine()) as db:db.get(Part,row['part_id']).archived=True;db.commit()
    assert activate(client,vehicle).json()['activated']==0
    assert available(client,vehicle,[row['id']],True).status_code==409


def test_workspace_and_employee_permissions(client,vehicle,monkeypatch):
    from conftest import signup
    from test_team import employee,activate as activate_employee
    fixture_catalogue(monkeypatch,[candidate('Safe')]);data=payload(client,vehicle)
    with TestClient(app) as other:
        signup(other,'another-workspace@example.test')
        assert other.get(path(vehicle)).status_code==404
        assert activate(other,vehicle,data).status_code==404
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    rights=['vehicles.view','inventory.view','catalog.view','dismantling.manage','inventory.create']
    row,credentials=employee(client,permissions=rights)
    with activate_employee(credentials) as worker:
        assert read(worker,vehicle)['total']==0
        assert activate(worker,vehicle,data).status_code==403
        from app.models import Account
        with Session(engine()) as db:
            a=db.get(Account,row['id']);a.permissions=rights+['inventory.activate_virtual'];db.commit()
        assert activate(worker,vehicle,data).status_code==200
        own=read(worker,vehicle)['items'][0]
        assert available(worker,vehicle,[own['id']],False).status_code==403
        # Still no platform-owner import permissions from workspace activation.
        assert worker.get('/api/v1/catalogue/admin/canonical/diagnostics').status_code==403


def test_order_reservation_consumption_and_disabled_draft(client,vehicle,monkeypatch):
    from test_orders import buyer,create,line,action
    fixture_catalogue(monkeypatch,[candidate('Safe')]);activate(client,vehicle)
    row=read(client,vehicle)['items'][0];p=client.get('/api/v1/parts/'+row['part_id']).json();b=buyer(client)
    order=create(client,b,[line(p)])
    assert available(client,vehicle,[row['id']],False).status_code==200
    assert action(client,order,'reserve').status_code==409
    assert action(client,order,'sell').status_code==409
    assert available(client,vehicle,[row['id']],True).status_code==200
    assert action(client,order,'reserve').status_code==200
    assert available(client,vehicle,[row['id']],False).status_code==409
    assert activate(client,vehicle).json()['activated']==0
    assert action(client,order,'sell').status_code==200
    s=read(client,vehicle)['items'][0]['stock'];assert s['quantity']==0 and s['reserved_quantity']==0 and s['state']=='sold'
    assert activate(client,vehicle).json()['activated']==0


def test_populated_upgrade_and_guarded_downgrade(client,vehicle,part,monkeypatch):
    import sys,subprocess
    from sqlalchemy import text
    def alembic(*args):return subprocess.run([sys.executable,'-m','alembic',*args],capture_output=True,text=True)
    before=client.get('/api/v1/parts/'+part['id']).json()
    assert alembic('downgrade','84d2c6fa190b').returncode==0
    assert alembic('upgrade','head').returncode==0
    assert client.get('/api/v1/parts/'+part['id']).json()==before
    assert alembic('upgrade','head').returncode==0
    fixture_catalogue(monkeypatch,[candidate('Safe')]);assert activate(client,vehicle).status_code==200
    with Session(engine()) as db:state=all_tables(db)
    r=alembic('downgrade','84d2c6fa190b');assert r.returncode!=0 and 'downgrade forbidden' in r.stderr
    with Session(engine()) as db:
        assert all_tables(db)==state
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='b7e14d90c2f6'


def test_legacy_receipts_sale_archive_exclusions_preserved_on_explicit_transition(client,vehicle,monkeypatch):
    from types import SimpleNamespace
    from app.services.dismantling import receipt
    from app.services import dismantling_plan_v3 as planner
    assert client.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start").status_code==200
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);generated=planner.preview(db,v,v.account_id,[],{})['items']
        rows=planner.rows_for(db,v);assert len(rows)==33;db.info['actor_id']=v.account_id
        for row in rows[:30]:
            row.status='dismantled';receipt(db,row,SimpleNamespace(quantity=1,condition='used',location='Local historical shelf',selling_price=None),row.account_id)
            p=db.get(Part,row.part_id);p.selling_price=137;p.unit_cost=17
        rows[0].included=False;rows[32].included=False
        excluded=rows[0].part_id;sold=rows[29].part_id;db.commit()
    assert operation(client,sold,'sale',1,sale_price='50.00',sale_currency='UAH').status_code==200
    with Session(engine()) as db:
        db.get(Part,sold).archived=True;db.commit()
        original={p.id:(p.quantity,p.reserved_quantity,p.selling_price,p.unit_cost,p.archived) for p in db.scalars(select(Part))}
        receipt_marks={r.id:(r.part_id,r.received_at,r.status,r.included) for r in planner.rows_for(db,db.get(Vehicle,vehicle['id']))}
        audit={o.id:(o.type,o.before,o.after) for o in db.scalars(select(Operation))}
    fixture_catalogue(monkeypatch,generated+[candidate('One new safe identity')])
    r=activate(client,vehicle);assert r.status_code==200,r.text
    assert r.json()['activated']==3,r.json()
    assert activate(client,vehicle).json()['activated']==0
    with Session(engine()) as db:
        for id,fields in original.items():
            p=db.get(Part,id);assert (p.quantity,p.reserved_quantity,p.selling_price,p.unit_cost,p.archived)==fields
        assert not db.get(Part,excluded).assortment_enabled
        for id,(part_id,received_at,status,included) in receipt_marks.items():
            row=db.get(DismantlingItem,id);assert (row.received_at,row.status,row.included)==(received_at,status,included)
            if part_id:assert row.part_id==part_id
        for id,fields in audit.items():
            o=db.get(Operation,id);assert (o.type,o.before,o.after)==fields


def test_existing_position_conflict_is_warning_not_deletion(client,vehicle,monkeypatch):
    from test_stage2d import items_with_conditions,TYPES
    tid=next(k for k,v in TYPES.items() if v['name']=='Свічка запалювання')
    items=[candidate('Свічка запалювання',tid=tid)]
    fixture_catalogue(monkeypatch,lambda c:items_with_conditions(items,c))
    def facts(value):return [dict(field='powertrain',value=value,kind='manual',reference='Owner configuration test',confidence='reported')]
    r=activate(client,vehicle,{**payload(client,vehicle),'facts':facts('petrol')});assert r.status_code==200,r.text
    before=read(client,vehicle)['items'][0]
    r=activate(client,vehicle,{**payload(client,vehicle),'facts':facts('diesel')});assert r.status_code==200,r.text
    after=read(client,vehicle)['items'][0]
    assert after['id']==before['id'] and after['part_id']==before['part_id']
    assert after['stock']['quantity']==1 and after['included']
    assert after['configuration_warning']
