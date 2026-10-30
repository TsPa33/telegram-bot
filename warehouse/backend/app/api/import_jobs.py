"""Owner-only, tenant-scoped durable analysis commands; publication is excluded."""
from typing import Literal
from fastapi import APIRouter,Query,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,func,text
from sqlalchemy.exc import IntegrityError
from app.api.catalogue import DB,Auth,Admin
from app.api.secure_route import SecureRoute
from app.models import ImportJob as Job,ImportJobEvent as Event
from app.models.catalogue import CatalogueJob as Upload
from sqlalchemy.orm import defer
from app.services import import_runner as runner

router=APIRouter(route_class=SecureRoute,prefix='/api/v1/admin/import-jobs',tags=['Durable analysis jobs'])
class Command(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_key:str=Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
class Create(Command):
    catalogue_job_id:str=Field(min_length=1,max_length=36)
    job_type:Literal['file_validation','catalogue_preview']

def submit_lock(db,account):
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:k)'),{'k':runner.lock_key(account)}):raise HTTPException(409,'Команда вже приймається; повторіть із тим самим ключем')

@router.post('',status_code=201)
def create(data:Create,db:DB,who:Auth,owner:Admin):
    try:j=runner.enqueue(db,who,data);db.commit();return runner.view(j)
    except IntegrityError:db.rollback();raise HTTPException(409,'Контекст або ключ уже існує; оновіть історію') from None

@router.get('')
def history(db:DB,who:Auth,owner:Admin,offset:int=Query(0,ge=0,le=100000),limit:int=Query(50,ge=1,le=100)):
    stmt=select(Job).where(Job.account_id==who.workspace_account_id).options(defer(Job.parameters))
    return dict(items=[runner.view(j,False) for j in db.scalars(stmt.order_by(Job.created_at.desc(),Job.id).offset(offset).limit(limit))],total=db.scalar(select(func.count()).select_from(Job).where(Job.account_id==who.workspace_account_id)),offset=offset,limit=limit)

@router.get('/inputs')
def inputs(db:DB,who:Auth,owner:Admin):
    rows=db.execute(select(Upload.id,Upload.filename,Upload.status,Upload.created_at).where(Upload.actor_id==who.actor_id,Upload.status!='failed').order_by(Upload.created_at.desc(),Upload.id).limit(100)).mappings()
    return dict(items=[dict(r) for r in rows],limit=100)

@router.get('/{id}')
def get(id:str,db:DB,who:Auth,owner:Admin):
    j=runner.owned(db,id,who.workspace_account_id)
    data=runner.view(j,False)
    metadata=db.execute(select(Job.parameters['catalogue_job_id'].as_string(),Job.parameters['payload_sha256'].as_string()).where(Job.id==j.id)).one()
    data['parameters']=dict(catalogue_job_id=metadata[0],payload_sha256=metadata[1]);return data

@router.get('/{id}/events')
def events(id:str,db:DB,who:Auth,owner:Admin,offset:int=Query(0,ge=0,le=100000),limit:int=Query(50,ge=1,le=100)):
    runner.owned(db,id,who.workspace_account_id)
    stmt=select(Event).where(Event.job_id==id)
    return dict(items=[dict(id=e.id,sequence=e.sequence,event_type=e.event_type,message=e.message,created_at=e.created_at,metadata=e.details) for e in db.scalars(stmt.order_by(Event.sequence).offset(offset).limit(limit))],total=db.scalar(select(func.count()).select_from(stmt.subquery())),offset=offset,limit=limit)

@router.post('/{id}/{action}')
def command(id:str,action:Literal['cancel','retry'],data:Command,db:DB,who:Auth,owner:Admin):
    submit_lock(db,who.workspace_account_id)
    try:j=runner.owned(db,id,who.workspace_account_id,True);runner.command(db,j,action,data.request_key);db.commit();return runner.view(j,False)
    except IntegrityError:db.rollback();raise HTTPException(409,'Контекст уже виконується') from None
