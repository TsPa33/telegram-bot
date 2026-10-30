"""R8.1 read-only global-owner projection and no-run parameter validation."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import Account
from app.models.catalogue import CatalogueOperation,CatalogueJob
from app.services.auth import hasher
from test_catalogue_v2 import platform,upload,plan,confirm,row
from test_v3_release_audit import all_tables
from conftest import signup


def parameters(**extra):return dict(source='aleto',manufacturer='Volvo',model='XC60',year_from=2018,year_to=2020,collect=['names','oem','prices','categories'],**extra)


def test_empty_overview_no_side_effects(platform):
    with Session(engine()) as db:before=all_tables(db)
    r=platform.get('/api/v1/catalogue/admin/overview');assert r.status_code==200,r.text
    d=r.json();assert d['sources']==[] and d['last_import'] is None and d['active_operations']==0
    assert d['new_price_observations_last_import'] is None and d['current_task'] is None
    assert not d['collection_history_available'] and not d['online_collection_enabled']
    assert all(not c['runner_connected'] and not c['approved_api'] and not c['approved_web_collection'] for c in d['capabilities'])
    with Session(engine()) as db:assert all_tables(db)==before


def test_applied_import_and_actual_progress(platform):
    j=upload(platform,[row()]);j=plan(platform,j);j=confirm(platform,j)
    d=platform.get('/api/v1/catalogue/admin/overview').json()
    assert d['last_import']['id']==j['id'] and d['new_price_observations_last_import']==1
    assert d['catalogue']==dict(offers=1,with_oem=1,with_prices=1) and d['sources'][0]['name']=='aleto'
    pending=upload(platform,[row('second')])
    accepted=platform.post('/api/v1/catalogue/admin/jobs/'+pending['id']+'/preview',json={});assert accepted.status_code==202
    with Session(engine()) as db:
        op=db.get(CatalogueOperation,accepted.json()['operation']['id']);op.status='running';op.progress={'phase':'planning','done':7,'total':20};db.commit();before=all_tables(db)
    d=platform.get('/api/v1/catalogue/admin/overview').json();assert d['active_operations']==1
    t=d['current_task'];assert t['kind']=='import_preview' and t['processed']==7 and t['total']==20 and t['unit']=='offer_groups' and t['valid_records'] is None
    assert 'session_hash' not in str(d) and 'rows' not in t
    with Session(engine()) as db:assert all_tables(db)==before


def test_validation_never_queues_or_fetches(platform,monkeypatch):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No source fetch permitted')))
    with Session(engine()) as db:before=all_tables(db)
    r=platform.post('/api/v1/catalogue/admin/parser/validate',json=parameters());assert r.status_code==200,r.text
    d=r.json();assert d['valid'] and not d['runnable'] and d['parameters']['model']=='XC60'
    with Session(engine()) as db:assert all_tables(db)==before


@pytest.mark.parametrize('change',[dict(year_from=2025,year_to=2018),dict(year_from=1800),dict(year_from='2018'),dict(source='unknown'),dict(manufacturer=''),dict(model=''),dict(collect=[]),dict(collect=['prices','prices']),dict(url='https://aleto.ua/search/'),dict(actor_id='other')])
def test_server_validation(platform,change):
    data=parameters();data.update(change)
    assert platform.post('/api/v1/catalogue/admin/parser/validate',json=data).status_code==422


def test_allowlist_and_csrf(platform,monkeypatch):
    owner=platform.get('/api/v1/auth/me').json()['id']
    monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS')
    assert platform.get('/api/v1/catalogue/admin/overview').status_code==403
    assert platform.post('/api/v1/catalogue/admin/parser/validate',json=parameters()).status_code==403
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner)
    with TestClient(app) as other:
        signup(other,'r81-other@example.test')
        assert other.get('/api/v1/catalogue/admin/overview').status_code==403
        assert other.post('/api/v1/catalogue/admin/parser/validate',json=parameters()).status_code==403
    with Session(engine()) as db:
        worker=Account(email='r81-worker@example.test',name='Worker',role='MANAGER',workspace_account_id=owner,permissions=['catalog.import','catalog.view'],password_hash=hasher.hash('local-reader-password'));db.add(worker);db.commit();wid=worker.id
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner+','+wid)
    with TestClient(app) as worker:
        login=worker.post('/api/v1/auth/login',json={'email':'r81-worker@example.test','password':'local-reader-password'});worker.headers['X-CSRF-Token']=login.json()['csrf_token']
        assert worker.get('/api/v1/catalogue/admin/overview').status_code==403
    platform.headers.pop('X-CSRF-Token')
    assert platform.post('/api/v1/catalogue/admin/parser/validate',json=parameters()).status_code==403


def test_canonical_operation_does_not_invent_progress(platform):
    from app.models.canonical import CanonicalRun
    actor=platform.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        run=CanonicalRun(actor_id=actor,session_hash='synthetic-not-a-real-session',mode='preview',status='queued',report={});db.add(run);db.commit();rid=run.id;before=all_tables(db)
    d=platform.get('/api/v1/catalogue/admin/overview').json();assert d['active_operations']==1
    assert d['current_task']['id']==rid and d['current_task']['kind']=='canonical_preview'
    assert d['current_task']['processed'] is None and d['current_task']['total'] is None
    with Session(engine()) as db:assert all_tables(db)==before


def test_parameter_validation_reuses_existing_throttle(platform):
    for _ in range(20):assert platform.post('/api/v1/catalogue/admin/parser/validate',json=parameters()).status_code==200
    assert platform.post('/api/v1/catalogue/admin/parser/validate',json=parameters()).status_code==429
    assert platform.get('/api/v1/catalogue/admin/overview').status_code==200
