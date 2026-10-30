"""Local synthetic source only: no permitted live access or network required."""
from copy import deepcopy
from uuid import uuid4
import json
from pathlib import Path
from threading import Event as Signal
import pytest
from sqlalchemy import select,text,func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from app.models import ImportJob,ImportJobArtifact
from app.models.catalogue import CatalogueJob
from app.services import aleto_adapter as adapter,import_runner as runner
from test_catalogue_v2 import platform
from test_import_runner import ROOT,key,get,cmd,expire
from test_v3_release_audit import all_tables
from conftest import signup


def create(c,model='XC60',request_key=None):
    response=c.post(ROOT,json=dict(job_type='aleto_offline',manufacturer='Volvo',model=model,request_key=request_key or key()))
    assert response.status_code==201,response.text
    return response.json()


def run(model='XC60',progress=lambda *args:None):
    return adapter.run_fixture(model,adapter.fixture(model)[1],progress)


def page(model='XC60'):
    return deepcopy(adapter.fixture(model)[0]['pages'][0])


def parse(p):return adapter.parse_page(p['html'],p['url'],p['observed_at'],'XC60')


@pytest.mark.parametrize('model',['XC40','XC60','XC90'])
def test_offline_extraction_report_and_provenance(model):
    summary,raw=run(model);artifact=json.loads(raw)
    assert summary['pages_checked']==2 and summary['offers_found']==2 and summary['duplicates']==1
    assert summary['with_oem']==1 and summary['with_prices']==2 and summary['error_count']==0
    assert summary['collection_completeness']=='fixture_pages_complete' and summary['live_collection_completeness']=='unverified'
    r=artifact['rows'][0]
    assert r['source_article']=='SYN-'+model+'-01' and r['oem']=='SYN-OEM-01'
    assert r['price_uah']=='2400.50' and r['price_usd']=='60.25'
    assert r['source']=='aleto-offline-fixture' and r['year_from'] is r['year_to'] is None
    assert r['observed_at']=='2026-01-15T12:00:00+00:00'
    assert r['source_record']['data_origin']=='synthetic_offline_fixture'
    assert len(artifact['records'])==3 and len(artifact['rows'])==2


@pytest.mark.parametrize('bad',['-20 грн','24 88 грн','free','12 EUR','1,234.56 грн','0 грн','NaN грн','10000000000 грн'])
def test_invalid_price_not_silently_repaired(bad):
    p=page();p['html']=p['html'].replace('2 400,50 грн',bad)
    result=parse(p)
    assert result['rows']==[] and result['issues'][0]['code']=='INVALID_PRICE'


@pytest.mark.parametrize('url',['','http://aleto.ua/part/x','https://aleto.ua.evil.test/x','https://user@aleto.ua/x','https://aleto.ua:444/x','https://127.0.0.1/x','//other.test/x','/ua/cart/x','/ua/%2e%2e/cart/','https://aleto.ua/x#fragment'])
def test_source_url_validation_never_falls_back(url):
    p=page();p['html']=p['html'].replace('/ua/part/synthetic-SYN-XC60-01/',url)
    result=parse(p)
    assert not result['rows'] and result['issues'][0]['code']=='INVALID_SOURCE_URL'


def test_missing_oem_never_uses_article_and_missing_price_is_unknown():
    p=page();p['html']=p['html'].replace('<small>Ориг. номер <b>SYN-OEM-01</b></small>','').replace('<span class="detail-item-uprice">2 400,50 грн</span>','').replace('<span class="detail-item-price">60.25 USD</span>','')
    r=parse(p)['rows'][0];assert r['oem']=='' and r['source_article']=='SYN-XC60-01'
    assert r['price_uah'] is r['price_usd'] is None


def test_broken_empty_and_unsupported_markup_is_not_successful_collection():
    p=page();p['html']='<html><div class="item">not verified markup'
    result=parse(p);assert not result['rows'] and result['issues'][0]['code']=='UNRECOGNIZED_OR_EMPTY_HTML'
    p['html']='<div>'*66
    with pytest.raises(ValueError,match='COMPLEXITY'):parse(p)
    p=page();p['html']='x'*(adapter.MAX_PAGE_BYTES+1)
    with pytest.raises(ValueError,match='PAGE_TOO_LARGE'):parse(p)
    p=page();p['observed_at']='2026-01-15T00:00:00'
    with pytest.raises(ValueError,match='TIMEZONE'):parse(p)


def test_manifest_checksum_changed_and_partial_pages(monkeypatch):
    with pytest.raises(ValueError,match='FIXTURE_CHANGED'):adapter.run_fixture('XC60','0'*64,lambda *a:None)
    f,checksum=adapter.fixture('XC60');f=deepcopy(f);f['pages']=f['pages'][:1]
    monkeypatch.setattr(adapter,'fixture',lambda m:(f,checksum))
    result,_=adapter.run_fixture('XC60',checksum,lambda *a:None)
    assert result['collection_completeness']=='partial_fixture' and result['error_count']==1


def test_conflicting_prices_are_not_last_write_wins(monkeypatch):
    f,checksum=adapter.fixture('XC60');f=deepcopy(f);f['pages'][1]['html']=f['pages'][1]['html'].replace('2 400,50 грн','2 999 грн')
    monkeypatch.setattr(adapter,'fixture',lambda m:(f,checksum))
    summary,raw=adapter.run_fixture('XC60',checksum,lambda *a:None)
    assert summary['conflicts']==1 and summary['collection_completeness']=='partial_fixture'
    assert [r['source_article'] for r in json.loads(raw)['rows']]==['SYN-XC60-02']


def snapshot():
    with Session(engine()) as db:return {k:v for k,v in all_tables(db).items() if k not in ('import_jobs','import_job_events','import_job_artifacts','catalogue_jobs','catalogue_operations')}


def test_queue_artifact_and_explicit_idempotent_file_handoff(platform):
    before=snapshot();k=key();j=create(platform,request_key=k)
    assert create(platform,request_key=k)['id']==j['id']
    assert platform.get(ROOT+'/'+j['id']+'/result').status_code==409
    assert runner.process_one(engine());done=get(platform,j);assert done['status']=='completed',done
    assert done['result_summary']['pages_checked']==2 and not done['result_summary']['live']
    result=platform.get(ROOT+'/'+j['id']+'/result');assert result.status_code==200
    assert adapter.sha(result.content)==result.headers['x-content-sha256']==done['result_summary']['artifact_sha256']
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(CatalogueJob))==0
    path=ROOT+'/'+j['id']+'/result/import'
    first=platform.post(path,json={'request_key':key()});assert first.status_code==200,first.text
    upload=first.json()['result_summary']['catalogue_job_id']
    assert platform.post(path,json={'request_key':key()}).json()['result_summary']['catalogue_job_id']==upload
    repeat=create(platform);assert runner.process_one(engine())
    assert platform.post(ROOT+'/'+repeat['id']+'/result/import',json={'request_key':key()}).json()['result_summary']['catalogue_job_id']==upload
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(CatalogueJob))==1
        rows=db.get(CatalogueJob,upload).rows;assert len(rows)==2 and all(r['source']=='aleto-offline-fixture' for r in rows)
    preview=platform.post('/api/v1/catalogue/admin/jobs/'+upload+'/preview',json={});assert preview.status_code==202
    from app.services.catalogue_jobs import process_one
    assert process_one(engine());saved=platform.get('/api/v1/catalogue/admin/jobs/'+upload).json()
    assert saved['status'] in ('ready','review') and saved['report']['committed'] is False
    assert snapshot()==before


def test_cancel_after_artifact_flush_rolls_back_all_results(platform,monkeypatch):
    j=create(platform);original=runner.execute_payload
    def cancel(db,j,progress):
        result=original(db,j,progress);db.flush()
        with Session(engine()) as other:
            row=other.get(ImportJob,j.id);runner.command(other,row,'cancel',key());other.commit()
        return result
    monkeypatch.setattr(runner,'execute_payload',cancel);assert runner.process_one(engine())
    assert get(platform,j)['status']=='cancelled'
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(ImportJobArtifact))==0


def test_interrupted_retry_and_missing_fixture(platform,monkeypatch):
    j=create(platform);stop=Signal();original=runner.adapter.run_fixture
    def interrupted(*args):result=original(*args);stop.set();return result
    with monkeypatch.context() as patch:
        patch.setattr(runner.adapter,'run_fixture',interrupted);assert runner.process_one(engine(),stop)
    assert get(platform,j)['status']=='queued'
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(ImportJobArtifact))==0
    assert runner.process_one(engine());assert get(platform,j)['attempt_count']==2 and get(platform,j)['status']=='completed'
    other=create(platform,'XC40')
    with monkeypatch.context() as patch:
        patch.setattr(adapter,'DIRECTORY',Path('/nonexistent-r83-fixtures'));assert runner.process_one(engine())
    assert get(platform,other)['status']=='failed'
    assert cmd(platform,other,'retry').status_code==200
    assert runner.process_one(engine()) and get(platform,other)['status']=='completed'


def test_artifact_integrity_and_tenant_permission_gates(platform,monkeypatch):
    j=create(platform);assert runner.process_one(engine());owner=platform.get('/api/v1/auth/me').json()['id']
    with TestClient(app) as other:
        signup(other,'adapter-other@example.test');oid=other.get('/api/v1/auth/me').json()['id']
        assert other.get(ROOT+'/'+j['id']+'/result').status_code==403
        monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner+','+oid)
        assert other.get(ROOT+'/'+j['id']+'/result').status_code==404
        assert other.post(ROOT+'/'+j['id']+'/result/import',json={'request_key':key()}).status_code==404
    for extra in ({'url':'https://aleto.ua'},{'mode':'approved_source'},{'model':'XC30'},{'catalogue_job_id':key()},{'code':'exec(1)'}):
        assert platform.post(ROOT,json=dict(job_type='aleto_offline',manufacturer='Volvo',model='XC60',request_key=key())|extra).status_code==422
    with Session(engine()) as db:
        row=db.get(ImportJob,j['id']);row.result_summary={**row.result_summary,'artifact_sha256':'0'*64};db.commit()
    assert platform.get(ROOT+'/'+j['id']+'/result').status_code==409
    platform.headers.pop('X-CSRF-Token');assert platform.post(ROOT+'/'+j['id']+'/result/import',json={'request_key':key()}).status_code==403


def test_small_storage_limit_and_immutable_content(platform,monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(adapter,'MAX_ARTIFACT_BYTES',5000)
        with pytest.raises(ValueError,match='STORAGE_LIMIT'):run()
    j=create(platform);assert runner.process_one(engine())
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError):
        with engine().begin() as c:c.execute(text('UPDATE import_job_artifacts SET content=:value'),{'value':b'tamper'})


def test_upgrade_from_r82_preserves_existing_queue_and_data(platform):
    import os,subprocess,sys
    from app.import_worker import schema_ready
    from test_catalogue_v2 import upload
    from test_import_runner import create as file_job
    old=file_job(platform,upload(platform))
    def migrate(*args):return subprocess.run([sys.executable,'-m','alembic',*args],capture_output=True,text=True,env=os.environ.copy())
    assert migrate('downgrade','c8f21d6e903a').returncode==0
    with Session(engine()) as db:before={k:v for k,v in all_tables(db).items() if k!='alembic_version'}
    assert not schema_ready(engine())
    result=migrate('upgrade','head');assert result.returncode==0,result.stderr
    with Session(engine()) as db:after={k:v for k,v in all_tables(db).items() if k not in ('alembic_version','import_job_artifacts')}
    assert before==after and schema_ready(engine())
    assert get(platform,old)['status']=='queued' and runner.process_one(engine())
    new=create(platform);assert runner.process_one(engine())
    assert migrate('downgrade','c8f21d6e903a').returncode!=0
    assert schema_ready(engine()) and get(platform,new)['status']=='completed'
