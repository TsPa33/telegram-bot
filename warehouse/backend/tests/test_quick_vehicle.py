"""Offline quick-create, isolation and additive migration against dedicated local DB."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from subprocess import run
import sys

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.main import app
from app.services import vehicle_catalog
from conftest import signup

QUICK = {'manufacturer':'Volvo','model':'XC90','year':2005}


def test_three_fields_with_disabled_provider(logged,monkeypatch):
    monkeypatch.setenv('PLAN_PARTS_ENABLED','false')
    r=logged.post('/api/v1/vehicles',json=QUICK)
    assert r.status_code==201
    row=r.json()
    assert row['donor_id'].startswith('AUTO-')
    assert row['acquisition_date'] is None and row['acquisition_cost'] is None
    assert row['ktype'] is None and row['engine']==''
    audit=logged.get('/api/v1/audit?vehicle_id='+row['id']).json()['items']
    assert any(a['type']=='vehicle_create' and a['after']['donor_id']==row['donor_id'] for a in audit)
    assert logged.get('/api/v1/parts').json()['total']==0


def test_ktype_and_explicit_zero_cost(logged):
    row=logged.post('/api/v1/vehicles',json={**QUICK,'ktype':9743,'acquisition_cost':0}).json()
    assert row['ktype']==9743 and Decimal(row['acquisition_cost'])==0
    assert row['acquisition_date'] is None
    assert logged.get('/api/v1/vehicles/'+row['id']+'/plan-parts-checklist').json()['total']==0


def test_local_names_are_partial_and_account_private(logged):
    logged.post('/api/v1/vehicles',json={'manufacturer':'Private Make','model':'Private Model','year':2000})
    data=logged.get('/api/v1/vehicle-catalog').json()
    assert data['complete'] is False
    assert next(b for b in data['brands'] if b['name']=='Volvo')['models']
    assert next(b for b in data['brands'] if b['name']=='Private Make')['models']==['Private Model']
    assert 'year_from' not in str(data) and 'ktype' not in str(data)
    with TestClient(app) as other:
        assert other.get('/api/v1/vehicle-catalog').status_code==401
        signup(other,'other-quick@example.test')
        assert not any(b['name']=='Private Make' for b in other.get('/api/v1/vehicle-catalog').json()['brands'])


def test_concurrent_creation_and_manual_duplicate(logged):
    def create(_):return logged.post('/api/v1/vehicles',json=QUICK)
    with ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(create,range(8)))
    assert all(r.status_code==201 for r in responses)
    ids=[r.json()['donor_id'] for r in responses]
    assert len(set(ids))==8
    assert logged.post('/api/v1/vehicles',json={**QUICK,'donor_id':ids[0]}).status_code==409


def test_auto_id_collision_retries(logged,monkeypatch):
    class ID:
        def __init__(self,value):self.hex=value
    values=iter(['collision','collision','unique'])
    monkeypatch.setattr(vehicle_catalog,'uuid4',lambda:ID(next(values)))
    assert logged.post('/api/v1/vehicles',json=QUICK).json()['donor_id']=='AUTO-collision'
    assert logged.post('/api/v1/vehicles',json=QUICK).json()['donor_id']=='AUTO-unique'


def test_minimal_edit_retains_secondary_data_and_stock(logged,vehicle,part):
    before=logged.get('/api/v1/parts/'+part['id']).json()
    original=logged.get('/api/v1/vehicles/'+vehicle['id']).json()
    body={k:original[k] for k in ('manufacturer','model','year')}
    edited=logged.put('/api/v1/vehicles/'+vehicle['id'],json=body).json()
    for field in ('donor_id','acquisition_date','acquisition_cost','notes','status','engine'):
        assert edited[field]==original[field]
    assert logged.get('/api/v1/parts/'+part['id']).json()==before
    assert logged.put('/api/v1/vehicles/'+vehicle['id'],json={**body,'donor_id':None}).status_code==422


def test_known_date_survives_nullable_migration(logged,vehicle,part):
    vehicle_before=logged.get('/api/v1/vehicles/'+vehicle['id']).json()
    part_before=logged.get('/api/v1/parts/'+part['id']).json()
    run([sys.executable,'-m','alembic','downgrade','a84d2c19e705'],check=True)
    try:
        run([sys.executable,'-m','alembic','upgrade','head'],check=True)
        assert logged.get('/api/v1/vehicles/'+vehicle['id']).json()==vehicle_before
        assert logged.get('/api/v1/parts/'+part['id']).json()==part_before
        run([sys.executable,'-m','alembic','check'],check=True)
    finally:run([sys.executable,'-m','alembic','upgrade','head'],check=True)


def test_downgrade_refuses_to_fabricate_unknown_dates(logged):
    row=logged.post('/api/v1/vehicles',json=QUICK).json()
    result=run([sys.executable,'-m','alembic','downgrade','a84d2c19e705'],capture_output=True,text=True)
    assert result.returncode!=0 and 'unknown acquisition dates' in result.stderr
    assert logged.get('/api/v1/vehicles/'+row['id']).json()['acquisition_date'] is None
    with engine().connect() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='021e8f6f220c'


def test_quick_create_still_checks_auth_csrf_and_validation(logged):
    assert logged.post('/api/v1/vehicles',json={**QUICK,'year':1700}).status_code==422
    assert logged.post('/api/v1/vehicles',json={**QUICK,'manufacturer':' '}).status_code==422
    logged.headers.pop('X-CSRF-Token')
    assert logged.post('/api/v1/vehicles',json=QUICK).status_code==403


def test_edit_keeps_checklist_status_and_stock(logged,vehicle,part):
    from app.api.plan_parts import plan_parts_client
    from app.services.plan_parts import CatalogPartType
    body={k:vehicle[k] for k in ('manufacturer','model','year')}
    logged.put('/api/v1/vehicles/'+vehicle['id'],json={**body,'ktype':9743})
    class Provider:
        def categories(self,account,ktype):return [CatalogPartType(pt_id=1,name='Oil filter',article_count=42)]
    app.dependency_overrides[plan_parts_client]=lambda:Provider()
    path='/api/v1/vehicles/'+vehicle['id']+'/plan-parts-checklist'
    try:
        assert logged.post(path).status_code==200
        item=logged.get(path).json()['items'][0]
        logged.patch(path+'/'+item['id'],json={'status':'present','name_uk':'Фільтр','notes':'Перевірено'})
        checklist_before=logged.get(path).json()
        part_before=logged.get('/api/v1/parts/'+part['id']).json()
        result=logged.put('/api/v1/vehicles/'+vehicle['id'],json={**body,'notes':'Лише додаткові дані','acquisition_date':None})
        assert result.status_code==200 and result.json()['ktype']==9743
        assert logged.get(path).json()==checklist_before
        assert logged.get('/api/v1/parts/'+part['id']).json()==part_before
        # Changing identity clears a potentially stale K-Type, preserving history.
        result=logged.put('/api/v1/vehicles/'+vehicle['id'],json={**body,'year':2001})
        assert result.json()['ktype'] is None
        assert logged.get(path+'?include_history=true').json()['items']==checklist_before['items']
    finally:app.dependency_overrides.pop(plan_parts_client,None)
