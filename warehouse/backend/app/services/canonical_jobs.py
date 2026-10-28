"""Durable explicit normalization runs, coordinated with the existing v2 worker."""
import logging
from fastapi import HTTPException
from sqlalchemy import select,text,update
from sqlalchemy.orm import Session
from app.models import now
from app.models.canonical import CanonicalRun as Run
from app.services.catalogue_jobs import WORKER_LOCK,authorize
from app.services.catalogue_import import LOCK
from app.services.canonical_catalogue import build
log=logging.getLogger(__name__)

def enqueue(db,who,mode,preview_id=None,token=None,request=None):
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK+2}):raise HTTPException(409,'Запит уже приймається')
    active=db.scalar(select(Run).where(Run.status.in_(['queued','running'])).limit(1))
    if active:
        if (active.mode,active.preview_id,active.token)==(mode,preview_id,token) and active.report.get('request')==request:return active
        raise HTTPException(409,'Нормалізація вже виконується')
    if mode=='publish':
        preview=db.get(Run,preview_id)
        if not preview or preview.mode!='preview' or preview.status!='done' or preview.token!=token or preview.report.get('kind')!=('rule-preview' if request and request.get('kind')=='rule-approve-request' else None):raise HTTPException(409,'Потрібна завершена перевірка нормалізації')
    run=Run(actor_id=who.actor_id,session_hash=who.session.token_hash,mode=mode,preview_id=preview_id,token=token,status='queued',report={'request':request} if request else {})
    db.add(run);db.flush();return run

def summary(run):
    return {k:getattr(run,k) for k in ('id','mode','status','preview_id','token','snapshot_sha','report','error','created_at','finished_at')}

def process_one(engine):
    with engine.connect() as coordinator:
        if not coordinator.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':WORKER_LOCK}):return False
        coordinator.commit()
        try:
            if not coordinator.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK}):coordinator.rollback();return False
            coordinator.execute(update(Run).where(Run.status=='running').values(status='error',error='Нормалізацію перервано. Опублікований каталог не змінено; повторіть явно.',finished_at=now()))
            coordinator.commit()
            with Session(engine) as db:
                run=db.scalar(select(Run).where(Run.status=='queued').order_by(Run.created_at,Run.id).limit(1))
                if not run:return False
                run.status='running';rid=run.id;db.commit()
            try:
                with Session(engine) as db:
                    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
                    run=db.get(Run,rid)
                    if run.status!='running':return True
                    authorize(db,run)
                    request=run.report.get('request') or {}
                    if request.get('kind')=='rule-preview-request':
                        from app.services.canonical_review import rule_preview
                        plan=rule_preview(db,request['draft'])
                    elif request.get('kind')=='rule-approve-request':
                        if request.get('confirm') is not True:raise HTTPException(422,'Потрібне явне підтвердження правила')
                        from app.services.canonical_review import approve_rule
                        plan=approve_rule(db,run.preview_id,run.token,run.actor_id)
                    else:plan=build(db,run.mode=='publish',run.preview_id,run.token)
                    run.report=plan['report'];run.token=plan['token'];run.snapshot_sha=plan['snapshot_sha']
                    run.status='done';run.finished_at=now();db.commit()
            except Exception as exc:
                message=exc.detail if isinstance(exc,HTTPException) else str(exc) if isinstance(exc,ValueError) else 'Помилка нормалізації; транзакцію скасовано'
                if not isinstance(exc,(HTTPException,ValueError)):log.exception('Canonical run %s failed',rid)
                with engine.begin() as conn:conn.execute(update(Run).where(Run.id==rid,Run.status=='running').values(status='error',error=str(message)[:1000],finished_at=now()))
            return True
        finally:
            coordinator.rollback();coordinator.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':WORKER_LOCK});coordinator.commit()
