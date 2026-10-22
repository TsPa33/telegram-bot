import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from subprocess import run
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.plan_parts import plan_parts_client
from app.main import app
from app.db import engine
from app.models import VehicleChecklistItem, Vehicle, Operation, Part
from app.services.plan_parts import CatalogPartType, PlanPartsClient, RequestGate
from app.services.checklists import generate
from conftest import signup


@pytest.fixture
def donor(logged, vehicle_data):
    return logged.post('/api/v1/vehicles',json={**vehicle_data,'donor_id':'PLAN-PARTS-TEST','ktype':9743}).json()


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('PLAN_PARTS_ENABLED','true')
    monkeypatch.setenv('PLAN_PARTS_API_KEY','offline-placeholder-not-a-real-key')
    payload=json.loads((Path(__file__).parent/'fixtures/plan_parts_categories_volvo_9743_632.json').read_text())
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.method=='GET'
        assert request.url.path=='/api/v1/aftermarket/catalog/categories'
        assert dict(request.url.params)=={'ktype':'9743'}
        return httpx.Response(200,json=payload)
    client=PlanPartsClient(httpx.MockTransport(handler))
    gate=RequestGate()
    class Provider:
        def categories(self,account,ktype):return client.categories(account,ktype,gate)
    app.dependency_overrides[plan_parts_client]=lambda:Provider()
    try:yield calls,payload
    finally:app.dependency_overrides.pop(plan_parts_client,None)


def path(donor):return f"/api/v1/vehicles/{donor['id']}/plan-parts-checklist"


def test_real_categories_create_separate_checklist_without_stock(logged,donor,provider):
    calls,_=provider
    assert calls==[]
    result=logged.post(path(donor))
    assert result.status_code==200
    assert result.json()['created']==632
    assert len(calls)==1
    data=logged.get(path(donor)+'?limit=200').json()
    assert data['total']==632 and data['synced'] is True
    assert all(row['status']=='unchecked' and row['name_uk']=='' for row in data['items'])
    assert all('quantity' not in row for row in data['items'])
    assert logged.get('/api/v1/parts').json()['total']==0
    assert logged.get('/api/v1/categories').json()['total']==0
    assert logged.post(path(donor)).json()['provider_requested'] is False
    assert len(calls)==1


def test_manual_checks_survive_refresh_and_missing_types(logged,donor):
    class Provider:
        rows=[CatalogPartType(pt_id=1,name='Same name',article_count=10),CatalogPartType(pt_id=2,name='Same name',article_count=20)]
        calls=0
        def categories(self,account,ktype):self.calls+=1;return self.rows
    provider=Provider()
    app.dependency_overrides[plan_parts_client]=lambda:provider
    try:
        logged.post(path(donor))
        rows=logged.get(path(donor)).json()['items']
        assert len(rows)==2 and rows[0]['id']!=rows[1]['id']
        item=next(row for row in rows if row['pt_id']==1)
        changed=logged.patch(path(donor)+'/'+item['id'],json={'status':'present','name_uk':'Моя назва','notes':'Перевірено вручну'})
        assert changed.status_code==200
        provider.rows=[CatalogPartType(pt_id=1,name='Updated provider name',article_count=100)]
        assert logged.post(path(donor)+'?refresh=true').status_code==200
        rows=logged.get(path(donor)).json()['items']
        assert len(rows)==2 # Missing pt_id=2 is not silently deleted.
        saved=next(row for row in rows if row['id']==item['id'])
        assert (saved['status'],saved['name_uk'],saved['notes'])==('present','Моя назва','Перевірено вручну')
        assert saved['name_en']=='Updated provider name' and saved['article_count']==100
        assert logged.get('/api/v1/parts').json()['total']==0
        assert logged.patch(path(donor)+'/'+item['id'],json={'quantity':10}).status_code==422
        audit=logged.get('/api/v1/audit?vehicle_id='+donor['id']).json()['items']
        assert any(row['type']=='checklist_update' for row in audit)
    finally:app.dependency_overrides.pop(plan_parts_client,None)


def test_other_account_cannot_read_import_or_update(logged,donor,provider):
    logged.post(path(donor))
    item=logged.get(path(donor)).json()['items'][0]
    calls,_=provider
    with TestClient(app) as other:
        signup(other,'other@example.test')
        assert other.get(path(donor)).status_code==404
        assert other.post(path(donor)).status_code==404
        assert other.patch(path(donor)+'/'+item['id'],json={'status':'absent'}).status_code==404
    assert len(calls)==1
    with TestClient(app) as anonymous:
        assert anonymous.get(path(donor)).status_code==401
        assert anonymous.post(path(donor)).status_code==401
    logged.headers.pop('X-CSRF-Token')
    assert logged.post(path(donor)+'?refresh=true').status_code==403
    assert logged.patch(path(donor)+'/'+item['id'],json={'status':'absent'}).status_code==403
    assert len(calls)==1


def test_missing_ktype_and_archived_vehicle_never_call_provider(logged,vehicle,provider):
    calls,_=provider
    assert logged.post(path(vehicle)).status_code==409
    logged.post('/api/v1/archive/vehicles/'+vehicle['id'])
    assert logged.post(path(vehicle)).status_code==404
    assert calls==[]


def test_empty_catalogue_is_not_refetched(logged,donor):
    class Provider:
        calls=0
        def categories(self,account,ktype):self.calls+=1;return []
    provider=Provider()
    app.dependency_overrides[plan_parts_client]=lambda:provider
    try:
        assert logged.post(path(donor)).json()['created']==0
        assert logged.get(path(donor)).json()['synced'] is True
        assert logged.post(path(donor)).json()['provider_requested'] is False
        assert provider.calls==1
    finally:app.dependency_overrides.pop(plan_parts_client,None)


def test_concurrent_generation_only_fetches_once(donor):
    class Provider:
        calls=0
        def categories(self,account,ktype):self.calls+=1;return [CatalogPartType(pt_id=1,name='Part',article_count=2)]
    provider=Provider()
    def invoke(_):
        with Session(engine()) as db:
            result=generate(db,donor['id'],donor['account_id'],provider)
            db.commit()
            return result['created']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(invoke,range(2)))==1
    assert provider.calls==1


def test_history_preserved_when_ktype_changes(logged,donor,vehicle_data):
    class Provider:
        calls=0
        def categories(self,account,ktype):self.calls+=1;return [CatalogPartType(pt_id=1,name='Part',article_count=2)]
    provider=Provider()
    app.dependency_overrides[plan_parts_client]=lambda:provider
    try:
        logged.post(path(donor));item=logged.get(path(donor)).json()['items'][0]
        logged.put('/api/v1/vehicles/'+donor['id'],json={**vehicle_data,'ktype':16063})
        data=logged.get(path(donor)).json()
        assert data['total']==0 and data['historical_total']==1
        assert logged.get(path(donor)+'?include_history=true').json()['total']==1
        assert logged.patch(path(donor)+'/'+item['id'],json={'status':'absent'}).status_code==409
        logged.post(path(donor))
        logged.put('/api/v1/vehicles/'+donor['id'],json={**vehicle_data,'donor_id':'PLAN-PARTS-TEST','ktype':9743})
        assert logged.post(path(donor)).json()['provider_requested'] is False
        assert provider.calls==2
    finally:app.dependency_overrides.pop(plan_parts_client,None)


def test_migration_preserves_existing_inventory(logged,donor,part):
    # Existing inventory and donor rows must survive the new additive migration.
    before=logged.get('/api/v1/parts/'+part['id']).json()
    run([sys.executable,'-m','alembic','downgrade','c91e72b6a410'],check=True)
    try:
        run([sys.executable,'-m','alembic','upgrade','head'],check=True)
        assert logged.get('/api/v1/parts/'+part['id']).json()==before
        assert logged.get('/api/v1/vehicles/'+donor['id']).json()['ktype']==9743
        run([sys.executable,'-m','alembic','check'],check=True)
    finally:run([sys.executable,'-m','alembic','upgrade','head'],check=True)


def test_provider_failure_leaves_no_partial_checklist(logged,donor):
    from app.services.plan_parts import PlanPartsError
    class Provider:
        def categories(self,account,ktype):raise PlanPartsError(504,'Plan.Parts тимчасово недоступний')
    app.dependency_overrides[plan_parts_client]=lambda:Provider()
    try:
        assert logged.post(path(donor)).status_code==504
        data=logged.get(path(donor)).json()
        assert data['total']==0 and data['synced'] is False
    finally:app.dependency_overrides.pop(plan_parts_client,None)


def test_database_rejects_cross_account_checklist(logged,donor):
    with TestClient(app) as other:account=signup(other,'unrelated@example.test')
    with Session(engine()) as db:
        db.add(VehicleChecklistItem(account_id=account['id'],vehicle_id=donor['id'],source='plan.parts',ktype=9743,pt_id=1,name_en='Part',article_count=0))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()


def test_categories_rate_limit_and_invalid_provider_data(logged,donor,provider):
    calls,payload=provider
    assert logged.post(path(donor)).status_code==200
    response=logged.post(path(donor)+'?refresh=true')
    assert response.status_code==429 and response.headers['Retry-After']=='60'
    assert len(calls)==1
    payload['data']['ktype']=16063
    transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))
    class Provider:
        def categories(self,account,ktype):return PlanPartsClient(transport).categories(account,ktype,RequestGate())
    app.dependency_overrides[plan_parts_client]=lambda:Provider()
    assert logged.post(path(donor)+'?refresh=true').status_code==502
    assert logged.get(path(donor)).json()['total']==632
