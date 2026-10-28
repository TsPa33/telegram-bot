"""Durable HTTP commands, worker coordination, disconnect and process-death recovery."""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from app.models import Session as AuthSession
from app.models.catalogue import CatalogueOperation as Operation,CatalogueOffer as Offer
from app.services.catalogue_jobs import process_one
from app.services.catalogue_import import Planner
from test_catalogue_v2 import platform,upload,plan,confirm,counts,original_fingerprints


def command(client,job,kind='preview',**changes):
    body={'resolutions':{}} if kind=='preview' else {'confirm':True,'preview_token':job['preview_token']}
    r=client.post(f"/api/v1/catalogue/admin/jobs/{job['id']}/{kind}",json={**body,**changes})
    assert r.status_code==202,r.text
    return r.json()


def get(client,job):return client.get('/api/v1/catalogue/admin/jobs/'+job['id']).json()


def test_short_durable_submission_duplicate_conflict_and_disconnect(platform):
    job=upload(platform)
    first=command(platform,job)
    assert first['operation']['status']=='queued' and counts()['catalogue_offers']==0
    assert command(platform,job)['operation']['id']==first['operation']['id']
    conflict=platform.post(f"/api/v1/catalogue/admin/jobs/{job['id']}/preview",json={'resolutions':{'different':{'action':'skip'}}})
    assert conflict.status_code==409
    # Worker has no Request/client dependency; a disconnected browser cannot cancel it.
    with TestClient(app) as disconnected:
        disconnected.cookies.update(platform.cookies)
        assert disconnected.get('/api/v1/catalogue/admin/jobs/'+job['id']).status_code==200
    assert process_one(engine())
    ready=get(platform,job)
    assert ready['status']=='ready' and ready['operation']['status']=='done'
    assert counts()['catalogue_offers']==0
    applied=command(platform,ready,'apply');process_one(engine())
    assert get(platform,job)['status']=='applied'
    assert command(platform,ready,'apply')['operation']['id']==applied['operation']['id']
    assert counts()['catalogue_offers']==1


def test_worker_does_not_block_api_and_other_workers_cannot_claim(platform,monkeypatch):
    job=upload(platform);command(platform,job)
    entered,release=Event(),Event();original=Planner.run
    def slow(self,rows):
        self.progress(0,len(rows),'planning');entered.set()
        assert release.wait(10)
        return original(self,rows)
    monkeypatch.setattr(Planner,'run',slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(process_one,engine())
        try:
            assert entered.wait(5)
            start=time.monotonic()
            assert get(platform,job)['operation']['status']=='running'
            assert platform.get('/api/v1/catalogue').status_code==200
            assert platform.get('/health').status_code==200
            assert command(platform,job)['operation']['status']=='running'
            assert not process_one(engine())
            assert time.monotonic()-start<2
        finally:release.set()
        assert future.result(timeout=10)
    assert get(platform,job)['status']=='ready'


@pytest.mark.parametrize('kind',['preview','apply'])
def test_process_death_rolls_back_and_requires_explicit_retry(platform,kind):
    job=upload(platform)
    if kind=='apply':job=plan(platform,job)
    command(platform,job,kind)
    script="""import os
from app.db import engine
from app.services.catalogue_jobs import process_one
from app.services.catalogue_import import Planner
original=Planner.persist
def crash(self):
 original(self)
 os._exit(57)
Planner.persist=crash
process_one(engine())
"""
    result=subprocess.run([sys.executable,'-c',script],env=dict(os.environ),capture_output=True,timeout=30)
    assert result.returncode==57,result.stderr.decode()
    assert get(platform,job)['operation']['status']=='running'
    assert counts()['catalogue_offers']==0
    process_one(engine()) # Recovery publishes error, never silently retries an apply.
    interrupted=get(platform,job)
    assert interrupted['operation']['status']=='error' and 'перезапуском' in interrupted['operation']['error']
    assert counts()['catalogue_offers']==0
    command(platform,job,kind);process_one(engine())
    assert get(platform,job)['operation']['status']=='done'
    assert counts()['catalogue_offers']==(1 if kind=='apply' else 0)


@pytest.mark.parametrize('revocation',['allowlist','session'])
def test_worker_rechecks_allowlist_and_session_before_execution(platform,monkeypatch,revocation):
    job=upload(platform);command(platform,job)
    if revocation=='allowlist':monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS')
    else:
        from sqlalchemy import delete
        with engine().begin() as conn:conn.execute(delete(AuthSession))
    process_one(engine())
    with Session(engine()) as db:
        op=db.scalar(select(Operation));assert op.status=='error' and 'відкликано' in op.error
    assert counts()['catalogue_offers']==0


def test_failed_bulk_apply_is_atomic_and_keeps_warehouse(platform,vehicle,part,monkeypatch):
    job=plan(platform,upload(platform))
    with Session(engine()) as db:before=original_fingerprints(db)
    original=Planner.persist
    def fail(self):original(self);raise ValueError('Synthetic post-write rollback test')
    monkeypatch.setattr(Planner,'persist',fail)
    command(platform,job,'apply');process_one(engine())
    result=get(platform,job)
    assert result['operation']['status']=='error' and 'Synthetic' in result['operation']['error']
    assert result['status']=='ready' and counts()['catalogue_offers']==0
    with Session(engine()) as db:assert original_fingerprints(db)==before
    monkeypatch.setattr(Planner,'persist',original)
    confirm(platform,job)


def test_queue_is_persistent_but_not_an_implicit_import(platform):
    job=upload(platform)
    assert not process_one(engine())
    assert get(platform,job)['status']=='uploaded'
    assert counts()['catalogue_offers']==0


def test_preview_has_no_speculative_global_dml_and_apply_batches(platform):
    from sqlalchemy import event
    from test_catalogue_v2 import row
    job=upload(platform,[row('bulk-'+str(i),part_name='Unique synthetic '+str(i)) for i in range(1000)])
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):statements.append(statement)
    event.listen(engine(),'before_cursor_execute',capture)
    try:
        ready=plan(platform,job)
        assert not any(s.startswith(('INSERT INTO catalogue_entities','INSERT INTO catalogue_offers','INSERT INTO catalogue_paths')) for s in statements)
        statements.clear()
        confirm(platform,ready)
        assert len(statements)<100
    finally:event.remove(engine(),'before_cursor_execute',capture)
    assert counts()['catalogue_offers']==1000


def test_coordinator_connection_loss_is_fenced_by_work_transaction(platform,monkeypatch):
    from sqlalchemy import event,text
    from sqlalchemy.exc import DBAPIError
    job=upload(platform);command(platform,job)
    entered,release=Event(),Event();original=Planner.run;pid=[]
    def capture(conn,cursor,statement,parameters,context,many):
        if 'pg_try_advisory_lock(' in statement:pid.append(conn.connection.driver_connection.info.backend_pid)
    def slow(self,rows):
        entered.set();assert release.wait(10);return original(self,rows)
    monkeypatch.setattr(Planner,'run',slow)
    event.listen(engine(),'before_cursor_execute',capture)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(process_one,engine())
        try:
            assert entered.wait(5) and pid
            with engine().begin() as conn:conn.execute(text('SELECT pg_terminate_backend(:pid)'),{'pid':pid[0]})
            # A second coordinator can acquire the worker lock but must not
            # recover/fail/retry the first worker's still-live work transaction.
            assert not process_one(engine())
            assert get(platform,job)['operation']['status']=='running'
        finally:
            release.set();event.remove(engine(),'before_cursor_execute',capture)
        with pytest.raises(DBAPIError):future.result(timeout=10)
    assert get(platform,job)['operation']['status']=='done'
    assert counts()['catalogue_offers']==0
    assert not process_one(engine())


def test_concurrent_http_submissions_enqueue_only_one_command(platform):
    job=upload(platform)
    def submit(_):
        return platform.post(f"/api/v1/catalogue/admin/jobs/{job['id']}/preview",json={'resolutions':{}})
    with ThreadPoolExecutor(max_workers=6) as pool:responses=list(pool.map(submit,range(12)))
    assert all(r.status_code in (202,409) for r in responses)
    assert len({r.json()['operation']['id'] for r in responses if r.status_code==202})==1
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Operation))==1
    process_one(engine())
    assert get(platform,job)['status']=='ready'
