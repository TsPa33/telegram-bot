"""PostgreSQL durable queue; one coordinated worker, isolated DB connections.

Only explicitly enqueued commands execute. Interrupted running commands become
errors after all old catalogue transactions release their lock; retry is explicit.
"""
import logging
import os
import threading
import time
from fastapi import HTTPException
from sqlalchemy import create_engine,select,text,update
from sqlalchemy.orm import Session,defer
from sqlalchemy.pool import NullPool
from app.config import database_url
from app.models import Account,Session as AuthSession,now
from app.models.catalogue import CatalogueJob as Job,CatalogueOperation as Operation
from app.services.catalogue_format import digest
from app.services.catalogue_import import preview,apply,platform_admin,LOCK

WORKER_LOCK=LOCK+1
log=logging.getLogger(__name__)


def enqueue(db,job_id,kind,command,who):
    # A different short lock serializes submissions, never waits for the planner.
    key=int(digest(['catalogue-submit',job_id])[:15],16)
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':key}):
        raise HTTPException(409,'Запит уже приймається; перевірте стан job')
    job=db.scalar(select(Job).where(Job.id==job_id).options(defer(Job.rows)))
    if not job:raise HTTPException(404,'Import job не знайдено')
    active=db.scalar(select(Operation).where(Operation.job_id==job_id,Operation.status.in_(['queued','running'])))
    if active:
        if active.kind==kind and active.command==command:return active
        raise HTTPException(409,'Операція вже очікує або виконується; перевірте стан job')
    if job.status=='failed':raise HTTPException(409,'Завантажте новий перевірений файл')
    if job.status=='applied':
        if kind=='apply' and command['preview_token']==job.preview_token:
            done=db.scalar(select(Operation).where(Operation.job_id==job_id,Operation.kind=='apply',Operation.status=='done').order_by(Operation.created_at.desc()))
            if done:return done
        raise HTTPException(409,'Імпорт уже застосовано')
    if kind=='apply' and (job.status!='ready' or command['preview_token']!=job.preview_token):
        raise HTTPException(409,'Потрібен новий preview')
    operation=Operation(job_id=job_id,actor_id=who.actor_id,session_hash=who.session.token_hash,
                        kind=kind,command=command,status='queued',progress={'phase':'queued','done':0,'total':0})
    db.add(operation);db.flush()
    return operation


def operation_summary(op,include_command=False):
    return dict(id=op.id,kind=op.kind,status=op.status,progress=op.progress,error=op.error,
                created_at=op.created_at,finished_at=op.finished_at,
                **({'submitted_resolutions':op.command.get('resolutions',{})} if include_command and op.kind=='preview' else {}))


def authorize(db,op):
    actor=db.scalar(select(Account).where(Account.id==op.actor_id).with_for_update(read=True))
    session=db.scalar(select(AuthSession).where(AuthSession.token_hash==op.session_hash).with_for_update(read=True))
    if not platform_admin(actor) or not session or session.account_id!=op.actor_id or session.expires_at<=now():
        raise HTTPException(403,'Доступ власника або сесію відкликано; увійдіть повторно')


def process_one(worker_engine):
    # Dedicated, session-scoped lock survives commits while publishing progress.
    # PostgreSQL releases it on process/connection death; other replicas cannot
    # declare an operation interrupted while its worker still owns this lock.
    with worker_engine.connect() as coordinator:
        if not coordinator.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':WORKER_LOCK}):return False
        coordinator.commit()
        try:
            # Wait-free recovery: an old transaction may outlive its coordinator.
            if not coordinator.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK}):
                coordinator.rollback();return False
            coordinator.execute(update(Operation).where(Operation.status=='running').values(
                status='error',error='Обробку перервано перезапуском. Дані не застосовано; перевірте job і повторіть дію явно.',finished_at=now()))
            coordinator.commit()
            with Session(worker_engine) as db:
                op=db.scalar(select(Operation).where(Operation.status=='queued').order_by(Operation.created_at,Operation.id).limit(1))
                if not op:return False
                op.status='running';op.progress={'phase':'starting','done':0,'total':0};oid=op.id
                db.commit()
            last=[0.0]
            def progress(done,total,phase):
                if time.monotonic()-last[0]<1 and done!=total:return
                last[0]=time.monotonic()
                # Never update the job row: the catalogue transaction owns it.
                with worker_engine.begin() as conn:
                    conn.execute(update(Operation).where(Operation.id==oid).values(progress={'phase':phase,'done':done,'total':total}))
            try:
                with Session(worker_engine) as db:
                    # Fence a worker whose coordinator connection was lost
                    # between claim and execution. Recovery takes this same lock.
                    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
                    op=db.get(Operation,oid)
                    if op.status!='running':return True
                    authorize(db,op)
                    if op.kind=='preview':preview(db,op.job_id,op.actor_id,op.command['resolutions'],progress)
                    else:apply(db,op.job_id,op.actor_id,op.command['preview_token'],progress)
                    # Same atomic commit as the catalogue, including crash after commit.
                    op.status='done';op.finished_at=now();op.progress={'phase':'complete','done':1,'total':1}
                    db.commit()
            except Exception as exc:
                message=exc.detail if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,ValueError) else 'Помилка обробки каталогу; транзакцію скасовано. Повторіть дію або зверніться до адміністратора.'
                if not isinstance(exc,(HTTPException,ValueError)):log.exception('Catalogue operation %s failed',oid)
                with worker_engine.begin() as conn:
                    conn.execute(update(Operation).where(Operation.id==oid,Operation.status=='running').values(status='error',error=str(message)[:1000],progress={'phase':'error','http_status':exc.status_code if isinstance(exc,HTTPException) else 422 if isinstance(exc,ValueError) else 500},finished_at=now()))
            return True
        finally:
            coordinator.rollback()
            coordinator.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':WORKER_LOCK});coordinator.commit()


def start_worker():
    stop=threading.Event()
    if os.getenv('WAREHOUSE_CATALOGUE_WORKER_ENABLED','true').lower()=='false':return stop,None
    def loop():
        worker_engine=create_engine(database_url(),poolclass=NullPool)
        try:
            while not stop.is_set():
                try:
                    worked=process_one(worker_engine)
                    if not worked:
                        from app.services.canonical_jobs import process_one as canonical_work
                        worked=canonical_work(worker_engine)
                except Exception:
                    log.exception('Catalogue worker unavailable');worked=False
                if not worked:stop.wait(1)
        finally:worker_engine.dispose()
    thread=threading.Thread(target=loop,name='catalogue-worker',daemon=True);thread.start()
    return stop,thread
