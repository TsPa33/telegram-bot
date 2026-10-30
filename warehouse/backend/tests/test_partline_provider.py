"""Provisional synthetic XML only. No official PartLine schema or live access claimed."""
from dataclasses import replace
from pathlib import Path
from threading import Event as Signal
import json
import pytest
from sqlalchemy import select,text,func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.db import engine
from app.main import app
from app.models import ImportJob,ImportJobArtifact
from app.services import partline_provider as provider,import_runner as runner
from test_catalogue_v2 import platform
from test_import_runner import ROOT,key,get,cmd
from test_v3_release_audit import all_tables
from conftest import signup


def create(c,article='SYN-PL-001',manufacturer='',request_key=None):
    response=c.post(ROOT,json=dict(job_type='partline_fixture',article=article,manufacturer=manufacturer,request_key=request_key or key()))
    assert response.status_code==201,response.text
    return response.json()


def response():return provider.TestResponse(provider.fixture_bytes()[0])


def parse(r=None,article='SYN-PL-001',manufacturer=''):return provider.parse_fixture(r or response(),article,manufacturer)


def snapshot():
    with Session(engine()) as db:return {k:v for k,v in all_tables(db).items() if k not in ('import_jobs','import_job_events','import_job_artifacts')}


def test_explicit_fixture_contract_fields_currencies_and_dedup():
    r=parse();assert r['offers_found']==2 and r['duplicates']==1 and r['external_requests']==0
    assert r['synthetic'] and not r['live'] and r['observed_at'] is None
    assert [(o['price'],o['currency']) for o in r['offers']]==[('1200.50','UAH'),('30.25','USD')]
    a=r['offers'][0]
    assert a['manufacturer']=='Synthetic Brand' and a['source_article']=='SYN-PL-001' and a['source']=='partline' and a['source_type']=='new_parts'
    assert a['original_name']=='Синтетичний новий фільтр' and a['quantity']==3
    assert a['request_status']=='fixture_only' and a['observed_at'] is None and a['oem_confirmed'] is False
    assert a['vehicle_compatibility']=='unverified' and not r['recommendation_eligible']


@pytest.mark.parametrize('article,manufacturer',[('unknown',''),('SYN-PL-001','Different Brand')])
def test_unknown_article_or_manufacturer_no_fallback(article,manufacturer):
    r=parse(article=article,manufacturer=manufacturer)
    assert r['offers']==[] and r['request_status']=='fixture_empty' and r['observed_at'] is None


def test_valid_empty_contract_response():
    r=parse(provider.TestResponse(b'<carpot-partline-fixture version="carpot-partline-fixture-v1" synthetic="true"/>'))
    assert r['offers_found']==0 and r['request_status']=='fixture_empty'


@pytest.mark.parametrize('body',[b'',b'<broken',b'<GetPrice><price>100</price></GetPrice>',b'<!DOCTYPE a [<!ENTITY x "many">]><a>&x;</a>',b'<!DOCTYPE a SYSTEM "https://127.0.0.1/secrets"><a/>',b'<carpot-partline-fixture version="carpot-partline-fixture-v1" synthetic="true"><xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="file:///etc/passwd"/></carpot-partline-fixture>',b'\xff\xfe<\x00x\x00>\x00'])
def test_invalid_xml_dtd_entities_unknown_official_shapes_rejected(body):
    with pytest.raises(provider.ProviderError,match='PARTLINE_INVALID_XML'):parse(provider.TestResponse(body))


@pytest.mark.parametrize('value',['-1','0','NaN','1,20','1e4','999999999999','20 USD','1.001'])
def test_invalid_price_is_not_repaired(value):
    raw=response().body.replace(b'1200.50',value.encode())
    with pytest.raises(provider.ProviderError,match='INVALID_OFFER'):parse(provider.TestResponse(raw))


@pytest.mark.parametrize('change,code',[(dict(status=401),'AUTH_ERROR'),(dict(status=403),'AUTH_ERROR'),(dict(status=429),'REJECTED'),(dict(status=500),'REJECTED'),(dict(status=302),'REJECTED'),(dict(elapsed_seconds=11),'TIMEOUT'),(dict(elapsed_seconds=float('nan')),'TIMEOUT'),(dict(content_type='text/html'),'INVALID_XML')])
def test_timeout_rejection_auth_and_redirects(change,code):
    with pytest.raises(provider.ProviderError,match=code):parse(replace(response(),**change))


def test_invalid_currency_quantity_and_size_limits():
    for raw in [response().body.replace(b'UAH',b'XYZ'),response().body.replace(b'<quantity>3',b'<quantity>-3')]:
        with pytest.raises(provider.ProviderError,match='INVALID_OFFER'):parse(provider.TestResponse(raw))
    with pytest.raises(provider.ProviderError,match='RESPONSE_LIMIT'):parse(provider.TestResponse(b'x'*(provider.MAX_BYTES+1)))


def test_live_never_enabled_by_configuration_or_client(monkeypatch):
    monkeypatch.setenv('PARTLINE_API_KEY','synthetic-never-logged-key');monkeypatch.setenv('PARTLINE_LIVE_ENABLED','true')
    assert provider.capabilities()['live_enabled'] is False
    with pytest.raises(provider.ProviderError,match='ACCESS_UNVERIFIED'):provider.live_lookup('genuine-article')
    for url in ['http://partline.com.ua/api/GetPrice','https://partline.com.ua.evil.test/api/GetPrice','https://partline.com.ua/api/GetPrice?key=secret','https://user:password@partline.com.ua/api/GetPrice','https://partline.com.ua:443/api/GetPrice','https://127.0.0.1/']:
        with pytest.raises(provider.ProviderError,match='ACCESS_UNVERIFIED'):provider.validate_reference_url(url)
    assert provider.validate_reference_url(provider.DOC_URL)==provider.DOC_URL


def test_real_queue_artifact_no_catalogue_seller_stock_finance_writes(platform):
    before=snapshot();k=key();j=create(platform,request_key=k)
    assert create(platform,request_key=k)['id']==j['id']
    assert runner.process_one(engine());done=get(platform,j);assert done['status']=='completed',done
    r=done['result_summary'];assert r['external_requests']==0 and r['offers_found']==2 and not r['recommendation_eligible']
    result=platform.get(ROOT+'/'+j['id']+'/result');assert result.status_code==200
    assert runner.adapter.sha(result.content)==r['artifact_sha256']==result.headers['x-content-sha256']
    assert 'SYNTHETIC' in result.headers['content-disposition']
    assert json.loads(result.content)['observed_at'] is None
    assert platform.post(ROOT+'/'+j['id']+'/result/import',json={'request_key':key()}).status_code==409
    assert snapshot()==before
    status=platform.get(ROOT+'/partline').json();assert not status['contract_verified'] and not status['live_enabled']


def test_cancel_after_result_flush_and_retry(platform,monkeypatch):
    j=create(platform);original=runner.execute_payload
    def cancelled(db,j,progress):
        result=original(db,j,progress);db.flush()
        with Session(engine()) as other:
            row=other.get(ImportJob,j.id);runner.command(other,row,'cancel',key());other.commit()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(runner,'execute_payload',cancelled);assert runner.process_one(engine())
    assert get(platform,j)['status']=='cancelled'
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(ImportJobArtifact))==0
    assert cmd(platform,j,'retry').status_code==200
    assert runner.process_one(engine());assert get(platform,j)['status']=='completed'


def test_changed_fixture_storage_and_sanitized_error_retry(platform,monkeypatch):
    j=create(platform)
    with monkeypatch.context() as patch:
        patch.setattr(provider,'FIXTURE',Path('/nonexistent-partline-r84.xml'));assert runner.process_one(engine())
    assert get(platform,j)['error_code']=='PARTLINE_STORAGE_UNAVAILABLE'
    assert '/nonexistent' not in get(platform,j)['error_message']
    assert cmd(platform,j,'retry').status_code==200
    assert runner.process_one(engine());assert get(platform,j)['status']=='completed'
    other=create(platform,'missing')
    with Session(engine()) as db:r=db.get(ImportJob,other['id']);r.parameters={**r.parameters,'fixture_sha256':'0'*64};db.commit()
    assert runner.process_one(engine());assert get(platform,other)['error_code']=='PARTLINE_FIXTURE_CHANGED'


def test_provider_concurrency_fence(platform):
    j=create(platform)
    with engine().connect() as conn:
        assert conn.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':provider.PROVIDER_SLOT});conn.commit()
        try:
            assert runner.process_one(engine());assert get(platform,j)['error_code']=='PARTLINE_BUSY'
        finally:conn.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':provider.PROVIDER_SLOT});conn.commit()
    assert cmd(platform,j,'retry').status_code==200
    assert runner.process_one(engine()) and get(platform,j)['status']=='completed'


def test_rate_limits_persist_and_replay_does_not_consume_new_job(platform):
    first=None
    for n in range(5):
        k=key();j=create(platform,'unknown-'+str(n),request_key=k)
        assert create(platform,'unknown-'+str(n),request_key=k)['id']==j['id']
        assert runner.process_one(engine())
    rejected=platform.post(ROOT,json=dict(job_type='partline_fixture',article='unknown-6',request_key=key()))
    assert rejected.status_code==429


def test_permissions_csrf_account_isolation_and_reject_live_params(platform,monkeypatch):
    j=create(platform);assert runner.process_one(engine());owner=platform.get('/api/v1/auth/me').json()['id']
    with TestClient(app) as other:
        signup(other,'partline-other@example.test');oid=other.get('/api/v1/auth/me').json()['id']
        assert other.get(ROOT+'/partline').status_code==403
        monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner+','+oid)
        assert other.get(ROOT+'/'+j['id']).status_code==404 and other.get(ROOT+'/'+j['id']+'/result').status_code==404
        assert cmd(other,j,'cancel').status_code==404
    for extra in ({'mode':'live'},{'url':provider.DOC_URL},{'api_key':'not-a-key'},{'account_id':'other'},{'article':['one','two']},{'job_type':'partline_live'},{'model':'XC60'}):
        response=platform.post(ROOT,json=dict(job_type='partline_fixture',article='SYN-PL-001',request_key=key())|extra);assert response.status_code==422,response.text
    platform.headers.pop('X-CSRF-Token');assert platform.post(ROOT,json=dict(job_type='partline_fixture',article='one',request_key=key())).status_code==403


def test_upgrade_preserves_existing_r83_data(platform):
    import os,subprocess,sys
    from app.import_worker import schema_ready
    from test_aleto_adapter import create as offline
    old=offline(platform);assert runner.process_one(engine())
    def migrate(*args):return subprocess.run([sys.executable,'-m','alembic',*args],env=os.environ.copy(),text=True,capture_output=True)
    assert migrate('downgrade','d3a82f1c904b').returncode==0
    with Session(engine()) as db:before={k:v for k,v in all_tables(db).items() if k!='alembic_version'}
    assert not schema_ready(engine())
    result=migrate('upgrade','head');assert result.returncode==0,result.stderr
    with Session(engine()) as db:after={k:v for k,v in all_tables(db).items() if k!='alembic_version'}
    assert before==after and schema_ready(engine())
    new=create(platform);assert runner.process_one(engine())
    assert migrate('downgrade','d3a82f1c904b').returncode!=0
    assert schema_ready(engine()) and get(platform,old)['status']=='completed'
