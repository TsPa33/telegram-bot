"""UX3: explicit direct receipts, durable identity, offline isolated test DB only."""
from concurrent.futures import ThreadPoolExecutor
from subprocess import run
import sys
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db import engine
from conftest import signup
from test_dismantling_v2 import catalog


def base(v):return '/api/v1/vehicles/'+v['id']+'/dismantling'
def prepare(c,v):
    assert c.post(base(v)+'/prepare',json={}).status_code==200
    return c.get(base(v)+'/workspace').json()
def confirmation(view):return {'selection_token':view['add_token'],'expected_count':view['add_count'],'quantity':1}


def test_automatic_catalog_direct_receipt_reload_and_audit(logged,vehicle):
    old=logged.post('/api/v1/parts',json={'vehicle_id':vehicle['id'],'name':'Old existing part'}).json()
    assert logged.post('/api/v1/parts/'+old['id']+'/operations',json={'type':'receipt','quantity':3,'reason':'Old stock'}).status_code==200
    data=prepare(logged,vehicle)
    assert data['counts']['included']==33 and data['add_count']==33
    assert logged.get('/api/v1/parts').json()['total']==1
    row=data['items'][0]
    assert logged.post(base(vehicle)+'/plan',json={'ids':[row['id']],'included':False}).status_code==200
    data=prepare(logged,vehicle);assert data['add_count']==32
    body=confirmation(data)
    result=logged.post(base(vehicle)+'/add-stock',json=body)
    assert result.status_code==200,result.text
    assert result.json()['updated']==32
    assert logged.post(base(vehicle)+'/add-stock',json=body).json()['updated']==0
    data=prepare(logged,vehicle)
    assert data['add_count']==0 and data['counts']['received']==32
    assert logged.get('/api/v1/parts/'+old['id']).json()['quantity']==3
    assert logged.get('/api/v1/parts').json()['total']==33
    with engine().connect() as db:
        assert db.execute(text("SELECT count(*) FROM operations WHERE type='receipt'")).scalar_one()==33
        assert db.execute(text("SELECT count(*) FROM operations WHERE type='dismantling_receipt'")).scalar_one()==32


def test_stale_selection_exclusion_csrf_ownership_and_archive(logged,vehicle):
    data=prepare(logged,vehicle);body=confirmation(data)
    logged.post(base(vehicle)+'/plan',json={'ids':[data['items'][0]['id']],'included':False})
    assert logged.post(base(vehicle)+'/add-stock',json=body).status_code==409
    assert logged.get('/api/v1/parts').json()['total']==0
    with TestClient(app) as other:
        assert other.post(base(vehicle)+'/prepare',json={}).status_code==401
        signup(other,'other@example.test')
        assert other.post(base(vehicle)+'/prepare',json={}).status_code==404
        assert other.post(base(vehicle)+'/add-stock',json=body).status_code==404
    csrf=logged.headers.pop('X-CSRF-Token')
    assert logged.post(base(vehicle)+'/prepare',json={}).status_code==403
    assert logged.post(base(vehicle)+'/add-stock',json=body).status_code==403
    logged.headers['X-CSRF-Token']=csrf
    logged.post('/api/v1/archive/vehicles/'+vehicle['id'])
    assert logged.post(base(vehicle)+'/prepare',json={}).status_code==200
    assert logged.post(base(vehicle)+'/add-stock',json=confirmation(logged.get(base(vehicle)+'/workspace').json())).status_code==404


def test_concurrent_direct_receipts(logged,vehicle):
    body=confirmation(prepare(logged,vehicle))
    cookies=dict(logged.cookies);headers=dict(logged.headers)
    def send(_):
        with TestClient(app) as c:
            c.cookies.update(cookies);c.headers.update(headers)
            r=c.post(base(vehicle)+'/add-stock',json=body)
            assert r.status_code==200,r.text
            return r.json()['updated']
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(send,range(2)))==[0,33]
    assert logged.get('/api/v1/parts').json()['total']==33


def test_large_catalog_receipt_is_atomic_and_not_limited_to_page(logged,vehicle):
    assert logged.post('/api/v1/dismantling/catalog/import',json=catalog(1001)).status_code==200
    data=prepare(logged,vehicle)
    assert data['add_count']==1034 and len(data['items'])==100
    filtered=logged.get(base(vehicle)+'/workspace?q=Test&type=ignored').json()
    assert filtered['add_token']==data['add_token'] and filtered['add_count']==1034
    r=logged.post(base(vehicle)+'/add-stock',json=confirmation(data))
    assert r.status_code==200,r.text
    assert r.json()['updated']==1034
    assert prepare(logged,vehicle)['add_count']==0
    assert logged.get('/api/v1/parts').json()['total']==1034
    assert logged.post(base(vehicle)+'/add-stock',json=confirmation(data)).json()['updated']==0


def test_vehicle_numbers_are_stable_account_local_and_not_mutable(logged,vehicle):
    assert vehicle['number']==1
    payload={'manufacturer':'Volvo','model':'XC90','year':2010}
    def create(_):
        with TestClient(app) as c:
            c.cookies.update(dict(logged.cookies));c.headers.update(dict(logged.headers))
            return c.post('/api/v1/vehicles',json=payload).json()
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(create,range(2)))
    assert sorted(r['number'] for r in rows)==[2,3]
    assert logged.get('/api/v1/vehicles?q=2').json()['total']>=1
    assert logged.put('/api/v1/vehicles/'+vehicle['id'],json={**payload,'number':99}).status_code==422
    with TestClient(app) as other:
        signup(other,'numbers@example.test')
        assert other.post('/api/v1/vehicles',json=payload).json()['number']==1
    assert logged.get('/api/v1/dismantling/simple-readiness').json()['contract_version']==3


def test_number_migration_preserves_existing_ids_stock_and_audit(logged,vehicle,part):
    with engine().connect() as db:
        old=db.execute(text('SELECT id, donor_id, account_id FROM vehicles')).all()
        count=db.execute(text('SELECT count(*) FROM operations')).scalar_one()
    run([sys.executable,'-m','alembic','downgrade','f06a41c9d2b7'],check=True)
    try:
        run([sys.executable,'-m','alembic','upgrade','head'],check=True)
        with engine().connect() as db:
            assert db.execute(text('SELECT id, donor_id, account_id FROM vehicles')).all()==old
            assert db.execute(text('SELECT number FROM vehicles')).scalar_one()==1
            assert db.execute(text('SELECT count(*) FROM operations')).scalar_one()==count
        assert logged.get('/api/v1/parts/'+part['id']).status_code==200
    finally:run([sys.executable,'-m','alembic','upgrade','head'],check=True)


def test_previous_backend_can_insert_without_number(logged,vehicle):
    # Old application writes all existing columns and omits only the new one.
    from uuid import uuid4
    with engine().begin() as db:
        columns=[r[0] for r in db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='vehicles' AND table_schema=current_schema() ORDER BY ordinal_position")) if r[0]!='number']
        names=', '.join('"'+c+'"' for c in columns)
        expressions=', '.join(':new_id' if c=='id' else ':donor' if c=='donor_id' else '"'+c+'"' for c in columns)
        db.execute(text(f'INSERT INTO vehicles ({names}) SELECT {expressions} FROM vehicles WHERE id=:id'),{'new_id':str(uuid4()),'donor':'old-backend-compatible','id':vehicle['id']})
        assert db.execute(text("SELECT number FROM vehicles WHERE donor_id='old-backend-compatible'")).scalar_one()==2
