"""Leased PostgreSQL analysis queue. No apply, publication, HTTP or raw-file storage."""
from datetime import timedelta
from uuid import uuid4
from decimal import Decimal
import threading,time
from fastapi import HTTPException
from sqlalchemy import select,func,text
from sqlalchemy.orm import Session,defer
from app.models import Account,ImportJob as Job,ImportJobEvent as Event,now
from app.models.catalogue import CatalogueJob as Upload
from app.models.import_runner import ImportJobArtifact
from app.services import aleto_adapter as adapter
from app.services.catalogue_format import digest,ImportRow,MAX_ROWS
from app.services.catalogue_import import platform_admin,LOCK,preview,locked_job

ACTIVE=('queued','running');LEASE_SECONDS=30;MAX_RUNTIME_SECONDS=300;SLOT_BASE=0x52383200
class Interrupted(Exception):pass
class BudgetExpired(Interrupted):pass
class InputUnavailable(Exception):pass

def clock(db):return db.scalar(select(func.clock_timestamp()))
def lock_key(id):return int(digest(['runner',id])[:15],16)
def event(db,j,kind,message,metadata=None,request_key=None):
    j.event_count+=1;db.add(Event(job_id=j.id,sequence=j.event_count,event_type=kind,message=message,details=metadata or {},request_key=request_key,created_at=clock(db)))
def view(j,detail=True):
    result={k:getattr(j,k) for k in ('id','account_id','source','job_type','status','created_by','created_at','started_at','finished_at','progress_current','progress_total','phase','result_summary','error_code','error_message','attempt_count','retry_count')}
    result['parameters']={k:v for k,v in j.parameters.items() if k!='resolutions'} if detail else {}
    return result
def owned(db,id,account,lock=False):
    stmt=select(Job).where(Job.id==id,Job.account_id==account).options(defer(Job.parameters))
    if lock:stmt=stmt.with_for_update().execution_options(populate_existing=True)
    j=db.scalar(stmt)
    if not j:raise HTTPException(404,'Завдання не знайдено')
    return j

def enqueue(db,who,data):
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:k)'),{'k':lock_key(who.workspace_account_id)}):raise HTTPException(409,'Запит уже приймається; повторіть із тим самим ключем')
    offline=data.job_type=='aleto_offline'
    fp=digest([data.job_type,data.manufacturer,data.model] if offline else [data.job_type,data.catalogue_job_id])
    old=db.scalar(select(Job).where(Job.account_id==who.workspace_account_id,Job.idempotency_key==data.request_key))
    if old:
        if old.fingerprint!=fp:raise HTTPException(409,'Ключ уже використано з іншими параметрами')
        return old
    if offline:
        if data.manufacturer!='Volvo' or data.model not in adapter.ROOTS:raise HTTPException(422,'Непідтримувана марка або модель')
        _,checksum=adapter.fixture(data.model)
        params=dict(manufacturer='Volvo',model=data.model,fixture_version=adapter.VERSION,fixture_sha256=checksum)
    else:
        upload=db.scalar(select(Upload).where(Upload.id==data.catalogue_job_id,Upload.actor_id==who.actor_id).options(defer(Upload.rows)))
        if not upload or upload.format=='rejected' or upload.status=='failed':raise HTTPException(404,'Потрібен власний збережений валідний upload')
        if data.job_type=='catalogue_preview' and upload.status=='applied':raise HTTPException(409,'Цей імпорт уже застосовано')
        params=dict(catalogue_job_id=upload.id,payload_sha256=upload.payload_sha256,resolutions=upload.resolutions if data.job_type=='catalogue_preview' else {})
    ctx=digest([data.job_type,params])
    if db.scalar(select(Job.id).where(Job.account_id==who.workspace_account_id,Job.context_hash==ctx,Job.status.in_(ACTIVE))):raise HTTPException(409,'Цей контекст уже в черзі; відкрийте історію')
    if db.scalar(select(func.count()).select_from(Job).where(Job.account_id==who.workspace_account_id,Job.status.in_(ACTIVE)))>=2:raise HTTPException(429,'Можна мати до двох активних задач')
    if db.scalar(select(func.count()).select_from(Job).where(Job.account_id==who.workspace_account_id,Job.created_at>clock(db)-timedelta(minutes=15)))>=20:raise HTTPException(429,'Ліміт 20 нових задач за 15 хвилин')
    j=Job(account_id=who.workspace_account_id,created_by=who.actor_id,source='aleto_fixture' if offline else 'file',job_type=data.job_type,parameters=params,status='queued',created_at=clock(db),idempotency_key=data.request_key,fingerprint=fp,context_hash=ctx,event_count=0)
    db.add(j);db.flush();event(db,j,'queued','Завдання збережено в черзі',{'actor_id':who.actor_id});return j

def command(db,j,action,key):
    prior=db.scalar(select(Event).where(Event.job_id==j.id,Event.request_key==key))
    if prior:
        if prior.event_type!=action:raise HTTPException(409,'Ключ команди вже використано')
        return j
    if action=='cancel':
        if j.status in ('completed','failed'):raise HTTPException(409,'Завершену задачу не можна скасувати')
        if j.status!='cancelled':
            j.status='cancelled';j.phase='cancelled';j.finished_at=clock(db);j.lease_owner=None;j.lease_until=None
    else:
        if j.status not in ('failed','cancelled'):raise HTTPException(409,'Повтор доступний лише після помилки або скасування')
        if j.attempt_count>=3 or j.retry_count>=3:raise HTTPException(409,'Ліміт повторів вичерпано')
        if db.scalar(select(Job.id).where(Job.id!=j.id,Job.account_id==j.account_id,Job.context_hash==j.context_hash,Job.status.in_(ACTIVE))):raise HTTPException(409,'Контекст уже виконується')
        if db.scalar(select(func.count()).select_from(Job).where(Job.account_id==j.account_id,Job.status.in_(ACTIVE)))>=2:raise HTTPException(429,'Можна мати до двох активних задач')
        j.status='queued';j.retry_count+=1;j.error_code=None;j.error_message=None;j.result_summary={};j.finished_at=None;j.progress_current=0;j.progress_total=None;j.phase='queued'
    event(db,j,action,'Запит скасування прийнято' if action=='cancel' else 'Безпечний повтор поставлено в чергу',request_key=key);return j

def recover(db):
    rows=list(db.scalars(select(Job).where(Job.status=='running',Job.lease_until<func.clock_timestamp()).order_by(Job.created_at).limit(50).with_for_update(skip_locked=True)))
    for j in rows:
        if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:k)'),{'k':lock_key(j.id)}):continue
        j.status='queued' if j.attempt_count<3 else 'failed';j.lease_owner=None;j.lease_until=None
        j.error_code=None if j.status=='queued' else 'ATTEMPTS_EXHAUSTED';j.error_message=None if j.status=='queued' else 'Ліміт відновлень вичерпано'
        j.finished_at=None if j.status=='queued' else clock(db);j.progress_current=0;j.progress_total=None;j.phase='queued' if j.status=='queued' else 'failed'
        event(db,j,'recovered','Прострочений lease відновлено',{'status':j.status})

def claim(db,conn,lease_seconds=LEASE_SECONDS):
    for j in db.scalars(select(Job).where(Job.status=='queued',Job.attempt_count<3,((Job.source=='file')&Job.job_type.in_(['file_validation','catalogue_preview']))|((Job.source=='aleto_fixture')&(Job.job_type=='aleto_offline'))).order_by(Job.created_at,Job.id).limit(20).with_for_update(skip_locked=True)):
        if not conn.scalar(text('SELECT pg_try_advisory_lock(:k)'),{'k':lock_key(j.id)}):continue
        j.status='running';j.attempt_count+=1;j.started_at=clock(db);j.finished_at=None;j.lease_owner=str(uuid4());j.lease_until=clock(db)+timedelta(seconds=lease_seconds);j.phase='starting';j.progress_current=0;j.progress_total=None;j.error_code=None;j.error_message=None
        event(db,j,'running','Worker отримав задачу',{'attempt':j.attempt_count});return j.id,j.lease_owner
    return None

def beat(engine,id,token,progress=None,lease_seconds=LEASE_SECONDS):
    with Session(engine) as db:
        db.execute(text("SET LOCAL statement_timeout='3000ms'"))
        j=db.scalar(select(Job).where(Job.id==id).with_for_update())
        if not j or j.status!='running' or j.lease_owner!=token or j.lease_until<=clock(db):return False
        actor=db.get(Account,j.created_by)
        if not platform_admin(actor) or actor.must_change_password or actor.id!=j.account_id:return False
        j.lease_until=clock(db)+timedelta(seconds=lease_seconds)
        if progress:
            done,total,phase=progress
            if (j.progress_current,j.progress_total,j.phase)!=(done,total,phase):
                j.progress_current=done;j.progress_total=total;j.phase=phase
                event(db,j,'progress','Оновлено фактичний прогрес',dict(current=done,total=total,phase=phase))
        db.commit();return True

def authorized(db,j,lock=False):
    stmt=select(Account).where(Account.id==j.created_by).execution_options(populate_existing=True)
    actor=db.scalar(stmt.with_for_update(read=True) if lock else stmt)
    if not platform_admin(actor) or actor.must_change_password or actor.id!=j.account_id:raise HTTPException(403,'Доступ ініціатора відкликано')

def analyze(rows,progress):
    if not rows or len(rows)>MAX_ROWS:raise ValueError('Invalid normalized row count')
    offers={};seen=set();duplicates=errors=0;issues=[]
    for i,raw in enumerate(rows):
        try:
            internal={'_raw_category','_raw_subcategory','_review_category','_review_subcategory'}
            if not isinstance(raw,dict):raise ValueError('Invalid row')
            for k in internal & raw.keys():
                if k.startswith('_review_') and type(raw[k]) is not bool:raise ValueError('Invalid review flag')
                if k.startswith('_raw_') and (not isinstance(raw[k],str) or len(raw[k])>4096):raise ValueError('Invalid provenance')
            r=ImportRow.model_validate({k:v for k,v in raw.items() if k not in internal}).model_dump(mode='json');ident=(r['source'],r['source_article']);h=digest(raw)
            if h in seen:duplicates+=1
            seen.add(h);o=offers.setdefault(ident,dict(oem=False,uah=False,usd=False));o['oem']|=bool((r.get('oem') or '').strip())
            for c in ('uah','usd'):o[c]|=r.get('price_'+c) is not None
        except (ValueError,TypeError):
            errors+=1
            if len(issues)<10:issues.append(dict(row=i+1,code='INVALID_NORMALIZED_ROW'))
        if (i+1)%250==0 or i+1==len(rows):progress(i+1,len(rows),'rows')
    return dict(input_rows=len(rows),unique_offers=len(offers),with_oem=sum(o['oem'] for o in offers.values()),with_prices=sum(o['uah'] or o['usd'] for o in offers.values()),priced_uah=sum(o['uah'] for o in offers.values()),priced_usd=sum(o['usd'] for o in offers.values()),exact_duplicate_rows=duplicates,error_count=errors,issues=issues,issues_truncated=errors>10,committed=False,validation_scope='persisted_normalized_rows_not_original_bytes')

def execute_payload(db,j,progress):
    if j.source=='aleto_fixture' and j.job_type=='aleto_offline':
        if j.parameters.get('manufacturer')!='Volvo' or j.parameters.get('fixture_version')!=adapter.VERSION:raise InputUnavailable()
        result,raw=adapter.run_fixture(j.parameters['model'],j.parameters['fixture_sha256'],progress)
        artifact=ImportJobArtifact(job_id=j.id,content=raw,sha256=adapter.sha(raw),size_bytes=len(raw),created_at=clock(db))
        db.add(artifact);db.flush()
        return dict(**result,artifact_id=artifact.id,artifact_sha256=artifact.sha256,artifact_bytes=artifact.size_bytes)
    if j.source!='file' or j.job_type not in ('file_validation','catalogue_preview'):raise InputUnavailable()
    if j.job_type=='catalogue_preview':
        if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:k)'),{'k':LOCK}):raise HTTPException(409,'Каталог зайнятий; повторіть задачу пізніше')
        upload,_=locked_job(db,j.parameters['catalogue_job_id'])
    else:upload=db.get(Upload,j.parameters['catalogue_job_id'])
    if not upload or upload.actor_id!=j.created_by or upload.payload_sha256!=j.parameters['payload_sha256'] or digest(upload.rows)!=upload.payload_sha256:raise InputUnavailable()
    if j.job_type=='file_validation':return analyze(upload.rows,progress)
    if upload.resolutions!=j.parameters['resolutions']:raise HTTPException(409,'Ручні рішення змінилися; створіть нову задачу')
    source=preview(db,upload.id,j.created_by,j.parameters['resolutions'],progress)
    r=source.report
    return dict(catalogue_job_id=source.id,preview_token=source.preview_token,status=source.status,counts=r['counts'],input_rows=r['input_rows'],unresolved_total=r['unresolved_total'],skipped_rows=r['skipped_rows'],duplicates=None,exact_duplicate_rows=len(upload.rows)-len({digest(r) for r in upload.rows}),conflicts=sum(i.get('kind')=='offer' for i in r['issues']) if not r['issues_truncated'] else None,committed=False)

def process_one(engine,stop=None):
    stop=stop or threading.Event()
    with engine.connect() as conn:
        slot=next((k for k in range(SLOT_BASE,SLOT_BASE+2) if conn.scalar(text('SELECT pg_try_advisory_lock(:k)'),{'k':k})),None)
        conn.commit()
        if slot is None:return False
        pair=None
        try:
            with Session(bind=conn) as db:recover(db);db.commit();pair=claim(db,conn);db.commit()
            if not pair:return False
            id,token=pair;lost=threading.Event();done=threading.Event();deadline=time.monotonic()+MAX_RUNTIME_SECONDS
            def heartbeat():
                while not done.wait(5):
                    try:
                        if stop.is_set() or time.monotonic()>=deadline or not beat(engine,id,token):lost.set();return
                    except Exception:lost.set();return
            thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
            def progress(current,total,phase):
                if time.monotonic()>=deadline:raise BudgetExpired()
                if lost.is_set() or stop.is_set() or not beat(engine,id,token,(current,total,phase)):raise Interrupted()
            try:
                with Session(bind=conn) as db:
                    db.execute(text("SET LOCAL statement_timeout='300000ms'"));db.execute(text("SET LOCAL lock_timeout='3000ms'"))
                    j=db.get(Job,id);authorized(db,j)
                    result=execute_payload(db,j,progress)
                    j=db.scalar(select(Job).where(Job.id==id).with_for_update().execution_options(populate_existing=True))
                    if time.monotonic()>=deadline:raise BudgetExpired()
                    if lost.is_set() or stop.is_set() or j.status!='running' or j.lease_owner!=token or j.lease_until<=clock(db):raise Interrupted()
                    authorized(db,j,True);j.status='completed';j.result_summary=result;j.finished_at=clock(db);j.phase='completed';j.lease_owner=None;j.lease_until=None
                    event(db,j,'completed','Аналіз завершено без застосування каталогу');db.commit()
            except Exception as exc:
                # Previous Session rolls back preview metadata as well as speculative data.
                with Session(bind=conn) as db:
                    j=db.scalar(select(Job).where(Job.id==id).with_for_update())
                    if j and j.status=='running' and j.lease_owner==token:
                        interrupted=stop.is_set() and j.attempt_count<3
                        j.status='queued' if interrupted else 'failed';j.phase=j.status;j.finished_at=None if interrupted else clock(db);j.lease_owner=None;j.lease_until=None
                        j.error_code='WORKER_STOPPED' if interrupted else 'TIME_LIMIT' if isinstance(exc,BudgetExpired) else 'INTERRUPTED' if isinstance(exc,Interrupted) else 'ACCESS_REVOKED' if isinstance(exc,HTTPException) and exc.status_code==403 else 'INPUT_UNAVAILABLE' if isinstance(exc,InputUnavailable) else 'PREVIEW_CONFLICT' if isinstance(exc,HTTPException) and exc.status_code==409 else 'INPUT_OR_PREVIEW_FAILED'
                        j.error_message='Виконання перервано; безпечний повтор доступний' if isinstance(exc,Interrupted) or interrupted else 'Перевірка недоступна: файл, рішення, доступ або каталог змінилися. Перевірте upload і повторіть.'
                        if interrupted:j.progress_current=0;j.progress_total=None
                        if j.job_type=='aleto_offline':
                            j.error_message='Offline-перевірку не завершено: fixture, доступ, контрольна сума або ліміт обробки. Каталог не змінено.'
                            if j.error_code=='INPUT_OR_PREVIEW_FAILED':
                                safe_codes={'FIXTURE_CHANGED','PAGE_TOO_LARGE','PAGE_LIMIT','RECORD_LIMIT','ARTIFACT_STORAGE_LIMIT','UNSUPPORTED_MODEL','INVALID_FIXTURE_MANIFEST'}
                                j.error_code=str(exc) if isinstance(exc,ValueError) and str(exc) in safe_codes else 'FIXTURE_UNAVAILABLE' if isinstance(exc,FileNotFoundError) else 'ADAPTER_INPUT_FAILED'
                            if j.error_code=='FIXTURE_CHANGED':j.error_message='Версія fixture змінилася після постановки в чергу. Створіть нову задачу.'
                            if j.error_code=='ARTIFACT_STORAGE_LIMIT':j.error_message='Результат перевищує 1 MiB. Для великих результатів потрібне стійке файлове сховище.'
                            if j.error_code=='FIXTURE_UNAVAILABLE':j.error_message='Пакет offline-fixture недоступний worker. Перевірте версію образу; результат не збережено.'
                        if isinstance(exc,InputUnavailable):j.error_message='Збережений upload недоступний або змінився. Завантажте файл повторно та створіть нову задачу.'
                        if isinstance(exc,BudgetExpired):j.error_message='Перевірка перевищила ліміт часу. Дані не застосовано.'
                        event(db,j,'requeued' if interrupted else 'failed',j.error_message,{'code':j.error_code});db.commit()
            finally:done.set();thread.join(4)
            return True
        finally:
            conn.rollback()
            # This dedicated execution connection owns only runner session locks.
            # Release even a lock acquired just before a failed claim commit.
            conn.execute(text('SELECT pg_advisory_unlock_all()'));conn.commit()
