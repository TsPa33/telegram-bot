"""R1: targeted characteristic writes, real disposable PostgreSQL, no external services."""
from concurrent.futures import ThreadPoolExecutor
from subprocess import run
import sys
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Account,Operation
from app.services.auth import hasher
from conftest import signup
from fastapi.testclient import TestClient
from app.main import app


def patch(c,p,values,expected):return c.patch('/api/v1/parts/'+p['id']+'/characteristics',json=dict(values=values,expected=expected))
def history(c,p):return c.get('/api/v1/audit?part_id='+p['id']).json()['items']

def test_sparse_idempotent_patch_preserves_every_other_value(logged,part):
    before=logged.get('/api/v1/parts/'+part['id']).json();old_history=history(logged,part)
    values={'color_name':'Сріблястий','paint_code':'714'};expected=dict(color_name=None,paint_code=None)
    r=patch(logged,part,values,expected);assert r.status_code==200,r.text
    after=r.json();assert {k:v for k,v in after.items() if k not in values}=={k:v for k,v in before.items() if k not in values}
    count=len(history(logged,part));assert count==len(old_history)+1
    assert patch(logged,part,values,expected).status_code==200
    assert len(history(logged,part))==count
    assert all(h in history(logged,part) for h in old_history)
    assert patch(logged,part,{'color_name':None},{'color_name':'Сріблястий'}).json()['paint_code']=='714'


def test_oem_cas_and_concurrency(logged,part):
    with ThreadPoolExecutor(2) as pool:responses=list(pool.map(lambda value:patch(logged,part,{'oem_number':value},{'oem_number':''}),['OEM-A','OEM-B']))
    assert sorted(r.status_code for r in responses)==[200,409]
    current=logged.get('/api/v1/parts/'+part['id']).json()['oem_number']
    assert patch(logged,part,{'oem_number':'OTHER'},{'oem_number':''}).status_code==409
    assert patch(logged,part,{'oem_number':current},{'oem_number':''}).status_code==200
    assert len([h for h in history(logged,part) if h['type']=='part_update'])==1


def test_validation_csrf_and_forbidden_fields(logged,part):
    for values,expected in [({},{}),({'color_name':'x'},{}),({'quantity':'2'},{'quantity':'0'}),({'color_name':'x'*81},{'color_name':None}),({'paint_code':'x'*41},{'paint_code':None}),({'oem_number':'x'*151},{'oem_number':''}),({'oem_number':'x\x00y'},{'oem_number':''})]:
        assert patch(logged,part,values,expected).status_code==422
    token=logged.headers.pop('X-CSRF-Token');assert patch(logged,part,{'color_name':'red'},{'color_name':None}).status_code==403;logged.headers['X-CSRF-Token']=token
    assert logged.get('/api/v1/parts/'+part['id']).json()['color_name'] is None
    assert logged.post('/api/v1/parts',json={'name':'Invalid color','color_name':'x\x00y'}).status_code==422


def test_worker_permissions_workspace_and_archive(logged,part):
    owner=logged.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        db.add(Account(email='r1-worker@example.test',name='Reader',password_hash=hasher.hash('r1-reader-password'),role='MANAGER',workspace_account_id=owner,permissions=['inventory.view']));db.commit()
    with TestClient(app) as reader:
        r=reader.post('/api/v1/auth/login',json={'email':'r1-worker@example.test','password':'r1-reader-password'});reader.headers['X-CSRF-Token']=r.json()['csrf_token']
        assert patch(reader,part,{'color_name':'red'},{'color_name':None}).status_code==403
    with TestClient(app) as other:
        signup(other,'r1-foreign@example.test');assert patch(other,part,{'color_name':'red'},{'color_name':None}).status_code==404
    assert logged.post('/api/v1/archive/parts/'+part['id']).status_code==200
    assert patch(logged,part,{'color_name':'red'},{'color_name':None}).status_code==404


def test_old_full_put_retains_colors_and_sparse_patch_preserves_finances(logged,part):
    assert patch(logged,part,{'color_name':'Blue','paint_code':'P-42'},{'color_name':None,'paint_code':None}).status_code==200
    r=logged.put('/api/v1/parts/'+part['id'],json={'name':part['name'],'selling_price':'50.00','unit_cost':'20.00','vehicle_id':part['vehicle_id']});assert r.status_code==200
    assert r.json()['color_name']=='Blue' and r.json()['paint_code']=='P-42'
    before=r.json();audit_before=history(logged,part)
    assert patch(logged,part,{'oem_number':'NEW'},{'oem_number':''}).status_code==200
    after=logged.get('/api/v1/parts/'+part['id']).json()
    for key in ['quantity','reserved_quantity','selling_price','currency','unit_cost','article_number','location','condition','availability']:assert after[key]==before[key]
    assert all(h in history(logged,part) for h in audit_before)


def test_populated_upgrade_additive_and_startup_repeat_safe(logged,part):
    with engine().connect() as c:before=c.execute(text("SELECT to_jsonb(parts)-'color_name'-'paint_code' FROM parts WHERE id=:id"),dict(id=part['id'])).scalar_one();ops=c.execute(text('SELECT count(*) FROM operations')).scalar_one()
    try:
        run([sys.executable,'-m','alembic','downgrade','a6d94c72e310'],check=True,capture_output=True)
        run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)
        run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)
        with engine().connect() as c:
            assert c.execute(text("SELECT to_jsonb(parts)-'color_name'-'paint_code' FROM parts WHERE id=:id"),dict(id=part['id'])).scalar_one()==before
            assert c.execute(text('SELECT count(*) FROM operations')).scalar_one()==ops
            assert c.execute(text('SELECT color_name,paint_code FROM parts WHERE id=:id'),dict(id=part['id'])).one()==(None,None)
    finally:run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)


def test_powertrain_existing_fields_do_not_change_stock(logged,vehicle,part):
    before=logged.get('/api/v1/parts/'+part['id']).json()
    r=logged.patch('/api/v1/vehicles/'+vehicle['id']+'/powertrain',json={'fuel_type':'Дизель','engine':'D4204T','transmission':'АКПП TG-81SC'});assert r.status_code==200,r.text
    assert r.json()['fuel_type']=='Дизель' and r.json()['engine']=='D4204T'
    assert logged.get('/api/v1/parts/'+part['id']).json()==before
    assert logged.patch('/api/v1/vehicles/'+vehicle['id']+'/powertrain',json={'fuel_type':'x'*51}).status_code==422


def test_populated_stock_and_historical_sale_are_immutable_during_characteristic_edit(logged,part):
    from uuid import uuid4
    base='/api/v1/parts/'+part['id']
    assert logged.post(base+'/operations',json={'type':'receipt','quantity':5,'reason':'Synthetic setup'}).status_code==200
    assert logged.post(base+'/operations',json={'type':'reserve','quantity':1,'reason':'Synthetic reserve'}).status_code==200
    assert logged.post(base+'/operations',json={'type':'sale','quantity':1,'sale_price':'12.34','sale_currency':'USD','reason':'Synthetic sale','request_key':str(uuid4())}).status_code==200
    before=logged.get(base).json();sales=logged.get('/api/v1/sales').json();audit=history(logged,part)
    assert patch(logged,part,{'color_name':'White','paint_code':'614','oem_number':'OE-77'},{'color_name':None,'paint_code':None,'oem_number':''}).status_code==200
    after=logged.get(base).json()
    assert {k:v for k,v in after.items() if k not in {'color_name','paint_code','oem_number'}}=={k:v for k,v in before.items() if k not in {'color_name','paint_code','oem_number'}}
    assert logged.get('/api/v1/sales').json()==sales
    assert all(h in history(logged,part) for h in audit)
