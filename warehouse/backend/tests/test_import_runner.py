"""Durable runner against disposable PostgreSQL only; no external source."""
from uuid import uuid4
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event as Signal
import pytest
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from app.models import ImportJob,ImportJobEvent,Account
from app.services import import_runner as runner
from app.models.catalogue import CatalogueJob,CatalogueOffer,CataloguePrice
from test_catalogue_v2 import platform,upload,row
from test_v3_release_audit import all_tables
from conftest import signup

ROOT='/api/v1/admin/import-jobs'
def key():return str(uuid4())
def create(c,source,kind='file_validation',request_key=None):
    r=c.post(ROOT,json=dict(catalogue_job_id=source['id'],job_type=kind,request_key=request_key or key()));assert r.status_code==201,r.text;return r.json()
def get(c,j):return c.get(ROOT+'/'+j['id']).json()
def cmd(c,j,action,k=None):return c.post(ROOT+'/'+j['id']+'/'+action,json={'request_key':k or key()})
def data_snapshot():
    with Session(engine()) as db:return {k:v for k,v in all_tables(db).items() if k not in ('import_jobs','import_job_events','catalogue_jobs')}

def test_create_replay_analyze_and_unchanged_data(platform):
    source=upload(platform,[row()]);before=data_snapshot();k=key();j=create(platform,source,request_key=k)
    assert create(platform,source,request_key=k)['id']==j['id']
    overview=platform.get('/api/v1/catalogue/admin/overview').json();assert overview['active_operations']==1 and overview['current_task']['id']==j['id'] and overview['current_task']['kind']=='runner_file_validation'
    assert platform.post(ROOT,json=dict(catalogue_job_id=source['id'],job_type='catalogue_preview',request_key=k)).status_code==409
    assert runner.process_one(engine())
    done=get(platform,j);assert done['status']=='completed',done
    assert done['result_summary']['unique_offers']==1 and done['result_summary']['with_oem']==1 and done['result_summary']['with_prices']==1
    assert done['result_summary']['priced_uah']==done['result_summary']['priced_usd']==1
    assert not done['result_summary']['committed'] and done['attempt_count']==1
    assert data_snapshot()==before
    events=platform.get(ROOT+'/'+j['id']+'/events').json()['items'];assert [e['sequence'] for e in events]==list(range(1,len(events)+1))
    assert events[-1]['event_type']=='completed'
    assert create(platform,source,request_key=k)['status']=='completed'

def test_preview_reuses_existing_dryrun_without_apply(platform):
    source=upload(platform,[row()]);before=data_snapshot();j=create(platform,source,'catalogue_preview')
    assert runner.process_one(engine());done=get(platform,j);assert done['status']=='completed',done
    report=done['result_summary'];assert report['counts']['offers']['inserted']==1 and not report['committed']
    saved=platform.get('/api/v1/catalogue/admin/jobs/'+source['id']).json();assert saved['status']=='ready' and saved['preview_token']==report['preview_token']
    assert data_snapshot()==before

def test_cancel_retry_and_command_replay(platform):
    source=upload(platform);j=create(platform,source);cancel_key=key()
    assert cmd(platform,j,'cancel',cancel_key).json()['status']=='cancelled'
    retry_key=key();assert cmd(platform,j,'retry',retry_key).json()['status']=='queued'
    assert cmd(platform,j,'cancel',cancel_key).json()['status']=='queued' # old cancel must not cancel new attempt
    assert cmd(platform,j,'retry',retry_key).json()['retry_count']==1
    assert runner.process_one(engine());assert get(platform,j)['status']=='completed'
    assert cmd(platform,j,'retry',retry_key).json()['status']=='completed'
    assert cmd(platform,j,'retry').status_code==409
    assert cmd(platform,j,'cancel').status_code==409

def expire(id):
    with Session(engine()) as db:j=db.get(ImportJob,id);j.lease_until=runner.clock(db)-timedelta(seconds=1);db.commit()

def test_expired_live_execution_is_not_claimed_twice(platform):
    source=upload(platform);j=create(platform,source);conn=engine().connect()
    with Session(bind=conn) as db:pair=runner.claim(db,conn);db.commit()
    assert pair[0]==j['id'];expire(j['id']);assert not runner.beat(engine(),*pair)
    assert not runner.process_one(engine());assert get(platform,j)['attempt_count']==1
    conn.invalidate();conn.close()
    assert runner.process_one(engine());done=get(platform,j);assert done['status']=='completed' and done['attempt_count']==2
    assert not runner.beat(engine(),*pair)

def test_heartbeat_and_progress_fenced_by_owner(platform):
    source=upload(platform);j=create(platform,source);conn=engine().connect()
    with Session(bind=conn) as db:pair=runner.claim(db,conn);db.commit()
    assert runner.beat(engine(),*pair,(1,10,'rows'))
    with Session(engine()) as db:r=db.get(ImportJob,j['id']);assert r.progress_current==1 and r.progress_total==10 and r.lease_until>runner.clock(db)+timedelta(seconds=20)
    assert not runner.beat(engine(),j['id'],key())
    conn.invalidate();conn.close();expire(j['id']);assert runner.process_one(engine())

def test_two_workers_can_process_distinct_jobs(platform,monkeypatch):
    import threading,time
    jobs=[create(platform,upload(platform,[row(str(i))])) for i in range(2)]
    barrier=threading.Barrier(2);original=runner.analyze
    def both(rows,progress):barrier.wait(10);return original(rows,progress)
    monkeypatch.setattr(runner,'analyze',both)
    def work():
        for _ in range(50):
            if runner.process_one(engine()):return
            time.sleep(.05)
        raise AssertionError('Worker did not claim')
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:work(),range(2)))
    assert all(get(platform,j)['status']=='completed' for j in jobs)
    assert all(get(platform,j)['attempt_count']==1 for j in jobs)

def test_cancel_rolls_back_preview_even_after_planner_returns(platform,monkeypatch):
    source=upload(platform);j=create(platform,source,'catalogue_preview');before=data_snapshot();entered=Signal();release=Signal();original=runner.execute_payload
    def paused(*args):
        result=original(*args);entered.set();assert release.wait(10);return result
    monkeypatch.setattr(runner,'execute_payload',paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(runner.process_one,engine());assert entered.wait(10)
        assert cmd(platform,j,'cancel').json()['status']=='cancelled';release.set();future.result(10)
    assert get(platform,j)['status']=='cancelled'
    saved=platform.get('/api/v1/catalogue/admin/jobs/'+source['id']).json();assert saved['status']=='uploaded' and saved['report']=={} and saved['preview_token'] is None
    assert data_snapshot()==before

def test_missing_storage_and_bounded_retry(platform):
    source=upload(platform);j=create(platform,source)
    with Session(engine()) as db:db.delete(db.get(CatalogueJob,source['id']));db.commit()
    for attempt in range(1,4):
        assert runner.process_one(engine());done=get(platform,j);assert done['status']=='failed' and done['attempt_count']==attempt
        if attempt<3:assert cmd(platform,j,'retry').json()['status']=='queued'
    assert cmd(platform,j,'retry').status_code==409 and done['error_code']=='INPUT_UNAVAILABLE'

def test_permissions_validation_and_cross_account(platform,monkeypatch):
    source=upload(platform);j=create(platform,source)
    for extra in ({'url':'https://aleto.ua/search/'},{'code':'print(1)'},{'account_id':'other'}):assert platform.post(ROOT,json=dict(catalogue_job_id=source['id'],job_type='file_validation',request_key=key(),**extra)).status_code==422
    assert platform.post(ROOT,json=dict(catalogue_job_id=source['id'],job_type='apply',request_key=key())).status_code==422
    owner=platform.get('/api/v1/auth/me').json()['id']
    with TestClient(app) as other:
        signup(other,'runner-other@example.test');oid=other.get('/api/v1/auth/me').json()['id']
        assert other.get(ROOT).status_code==403
        monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner+','+oid)
        assert other.get(ROOT).json()['total']==0
        assert other.get(ROOT+'/'+j['id']).status_code==404 and other.get(ROOT+'/'+j['id']+'/events').status_code==404
        assert cmd(other,j,'cancel').status_code==404
        assert other.post(ROOT,json=dict(catalogue_job_id=source['id'],job_type='file_validation',request_key=key())).status_code==404
    platform.headers.pop('X-CSRF-Token');assert cmd(platform,j,'cancel').status_code==403

@pytest.mark.parametrize('job_type',['file_validation','catalogue_preview','aleto_offline','partline_fixture'])
def test_real_process_death_recovery(platform,job_type):
    import os,subprocess,sys,select
    if job_type=='partline_fixture':
        from test_partline_provider import create as partline
        j=partline(platform)
    elif job_type=='aleto_offline':
        from test_aleto_adapter import create as offline
        j=offline(platform)
    else:
        source=upload(platform);j=create(platform,source,job_type)
    code="""
import time
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from app.config import database_url
from app.services import import_runner as runner
original=runner.execute_payload
def hold(db,*args):
 result=original(db,*args)
 db.flush()
 print('CLAIMED',flush=True)
 time.sleep(60)
 return result
runner.execute_payload=hold
runner.process_one(create_engine(database_url(),poolclass=NullPool))
"""
    child=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=os.environ.copy())
    try:
        assert select.select([child.stdout],[],[],15)[0] and child.stdout.readline().strip()==b'CLAIMED'
        child.kill();child.wait(5);expire(j['id']);assert runner.process_one(engine());done=get(platform,j)
        assert done['status']=='completed' and done['attempt_count']==2
    finally:
        if child.poll() is None:child.kill();child.wait(5)

def test_active_duplicate_and_limits(platform):
    source=upload(platform);create(platform,source)
    assert platform.post(ROOT,json=dict(catalogue_job_id=source['id'],job_type='file_validation',request_key=key())).status_code==409
    create(platform,source,'catalogue_preview');another=upload(platform,[row('other')])
    assert platform.post(ROOT,json=dict(catalogue_job_id=another['id'],job_type='file_validation',request_key=key())).status_code==429

def test_shutdown_requeues_without_duplicate_result(platform,monkeypatch):
    source=upload(platform);j=create(platform,source);stop=Signal();original=runner.analyze
    def interrupted(rows,progress):
        result=original(rows,progress);stop.set();return result
    with monkeypatch.context() as patch:
        patch.setattr(runner,'analyze',interrupted);assert runner.process_one(engine(),stop)
    assert get(platform,j)['status']=='queued' and get(platform,j)['attempt_count']==1
    assert runner.process_one(engine());assert get(platform,j)['status']=='completed' and get(platform,j)['attempt_count']==2

def test_runtime_budget_and_authorization_revocation(platform,monkeypatch):
    source=upload(platform);j=create(platform,source)
    with monkeypatch.context() as patch:
        patch.setattr(runner,'MAX_RUNTIME_SECONDS',0);assert runner.process_one(engine())
    assert get(platform,j)['status']=='failed' and get(platform,j)['error_code']=='TIME_LIMIT'
    assert cmd(platform,j,'retry').status_code==200
    owner=platform.get('/api/v1/auth/me').json()['id'];monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS','')
    assert runner.process_one(engine())
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner)
    assert get(platform,j)['status']=='failed' and get(platform,j)['error_code']=='ACCESS_REVOKED'

def test_max_expired_attempts_and_immutable_events(platform):
    from sqlalchemy.exc import DBAPIError
    source=upload(platform);j=create(platform,source)
    with Session(engine()) as db:
        r=db.get(ImportJob,j['id']);r.status='running';r.attempt_count=3;r.lease_owner=key();r.lease_until=runner.clock(db)-timedelta(seconds=1);db.commit()
    assert not runner.process_one(engine());assert get(platform,j)['status']=='failed'
    assert get(platform,j)['error_code']=='ATTEMPTS_EXHAUSTED' and cmd(platform,j,'retry').status_code==409
    with pytest.raises(DBAPIError):
        with engine().begin() as db:db.execute(text('UPDATE import_job_events SET message=:m WHERE job_id=:id'),{'m':'tamper','id':j['id']})

def test_additive_upgrade_preserves_populated_old_tables(platform,vehicle):
    import subprocess,sys,os
    from test_orders import stocked
    from app.import_worker import schema_ready
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    part=stocked(platform,vehicle,quantity=3)
    assert platform.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'sale','quantity':1,'sale_price':'55.00','sale_currency':'USD','request_key':key()}).status_code==200
    from test_catalogue_v2 import plan,confirm
    old_upload=upload(platform);confirm(platform,plan(platform,old_upload))
    scripts=ScriptDirectory.from_config(Config('alembic.ini'));assert scripts.get_heads()==['f5c84d31a620'] and scripts.get_revision('c8f21d6e903a').down_revision=='b7e14d90c2f6'
    def alembic(*args):return subprocess.run([sys.executable,'-m','alembic',*args],capture_output=True,text=True,env=os.environ.copy())
    assert alembic('downgrade','b7e14d90c2f6').returncode==0
    assert not schema_ready(engine())
    with Session(engine()) as db:before={k:v for k,v in all_tables(db).items() if k!='alembic_version'}
    assert alembic('upgrade','head').returncode==0 and schema_ready(engine())
    with Session(engine()) as db:after={k:v for k,v in all_tables(db).items() if k not in ('alembic_version','import_jobs','import_job_events','import_job_artifacts')}
    assert before==after
    create(platform,upload(platform))
    assert alembic('downgrade','b7e14d90c2f6').returncode!=0
    assert schema_ready(engine())

def test_runner_preview_supersedes_old_terminal_operation_not_new_active_one(platform):
    from app.models.catalogue import CatalogueOperation
    source=upload(platform);owner=platform.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        db.add(CatalogueOperation(job_id=source['id'],actor_id=owner,session_hash='synthetic-old-session',kind='preview',status='error',command={'resolutions':{}},progress={},error='Synthetic previous failure',created_at=runner.now()-timedelta(days=1)));db.commit()
    j=create(platform,source,'catalogue_preview');assert runner.process_one(engine())
    assert get(platform,j)['status']=='completed'
    source_view=platform.get('/api/v1/catalogue/admin/jobs/'+source['id']).json()
    assert source_view['operation']['id']==j['id'] and source_view['operation']['origin']=='import_runner'
    assert source_view['operation']['status']=='done' and source_view['operation']['submitted_resolutions']=={}
    history=platform.get('/api/v1/catalogue/admin/jobs').json()['items']
    assert history[0]['operation']['id']==j['id']
    newer=platform.post('/api/v1/catalogue/admin/jobs/'+source['id']+'/preview',json={});assert newer.status_code==202
    assert platform.get('/api/v1/catalogue/admin/jobs/'+source['id']).json()['operation']['id']==newer.json()['operation']['id']

def test_existing_legacy_provenance_is_not_rejected(platform):
    import json
    source=upload(platform,[{**row(),'source_record':json.dumps(dict(article='demo-1',category='Кузов',subcategory='Бампери'))}])
    with Session(engine()) as db:assert '_raw_category' in db.get(CatalogueJob,source['id']).rows[0]
    j=create(platform,source);assert runner.process_one(engine());done=get(platform,j)
    assert done['status']=='completed' and done['result_summary']['error_count']==0
    assert done['result_summary']['unique_offers']==1

def test_history_does_not_load_frozen_resolution_payloads(platform):
    from sqlalchemy import event
    source=upload(platform);j=create(platform,source,'catalogue_preview');queries=[]
    def capture(conn,cursor,statement,parameters,context,many):queries.append(statement)
    event.listen(engine(),'before_cursor_execute',capture)
    try:
        result=platform.get(ROOT);assert result.status_code==200
        assert result.json()['items'][0]['parameters']=={}
    finally:event.remove(engine(),'before_cursor_execute',capture)
    assert not any('import_jobs.parameters' in q for q in queries)
