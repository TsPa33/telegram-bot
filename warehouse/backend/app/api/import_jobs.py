"""Owner-only, tenant-scoped durable analysis commands; publication is excluded."""
from typing import Literal
from fastapi import APIRouter,Query,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from fastapi.responses import Response
import json
from sqlalchemy import select,func,text
from sqlalchemy.exc import IntegrityError
from app.api.catalogue import DB,Auth,Admin
from app.api.secure_route import SecureRoute
from app.models import ImportJob as Job,ImportJobEvent as Event,ImportJobArtifact as Artifact
from app.models.catalogue import CatalogueJob as Upload
from sqlalchemy.orm import defer
from app.services import import_runner as runner

router=APIRouter(route_class=SecureRoute,prefix='/api/v1/admin/import-jobs',tags=['Durable analysis jobs'])
class Command(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_key:str=Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
class Create(Command):
    catalogue_job_id:str|None=Field(default=None,min_length=1,max_length=36)
    job_type:Literal['file_validation','catalogue_preview','aleto_offline','partline_fixture']
    manufacturer:str|None=Field(default=None,max_length=100)
    article:str|None=Field(default=None,min_length=1,max_length=100)
    model:Literal['XC40','XC60','XC90']|None=None

    @model_validator(mode='after')
    def context(self):
        if self.job_type=='partline_fixture':
            if self.catalogue_job_id is not None or self.model is not None:raise ValueError('PartLine accepts one article and optional manufacturer only')
            self.article=runner.partline.query_text(self.article)
            self.manufacturer=runner.partline.query_text(self.manufacturer,True)
        elif self.article is not None:raise ValueError('Article only belongs to PartLine fixture context')
        elif self.job_type=='aleto_offline':
            if self.catalogue_job_id is not None or self.manufacturer!='Volvo' or not self.model:raise ValueError('Offline requires Volvo/model only')
        elif not self.catalogue_job_id or self.manufacturer is not None or self.model is not None:raise ValueError('File jobs require only a saved upload')
        return self

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

@router.get('/partline')
def partline_status(db:DB,who:Auth,owner:Admin):return runner.partline.capabilities()

@router.get('/{id}')
def get(id:str,db:DB,who:Auth,owner:Admin):
    j=runner.owned(db,id,who.workspace_account_id)
    data=runner.view(j,False)
    metadata=db.execute(select(Job.parameters['catalogue_job_id'].as_string(),Job.parameters['payload_sha256'].as_string()).where(Job.id==j.id)).one()
    data['parameters']=dict(catalogue_job_id=metadata[0],payload_sha256=metadata[1])
    if j.job_type=='aleto_offline':
        params=db.execute(select(Job.parameters['manufacturer'].as_string(),Job.parameters['model'].as_string(),Job.parameters['fixture_version'].as_string()).where(Job.id==j.id)).one()
        data['parameters']=dict(manufacturer=params[0],model=params[1],fixture_version=params[2])
    if j.job_type=='partline_fixture':
        params=db.execute(select(Job.parameters['article'].as_string(),Job.parameters['manufacturer'].as_string(),Job.parameters['mode'].as_string()).where(Job.id==j.id)).one()
        data['parameters']=dict(article=params[0],manufacturer=params[1],mode=params[2])
    return data

@router.get('/{id}/events')
def events(id:str,db:DB,who:Auth,owner:Admin,offset:int=Query(0,ge=0,le=100000),limit:int=Query(50,ge=1,le=100)):
    runner.owned(db,id,who.workspace_account_id)
    stmt=select(Event).where(Event.job_id==id)
    return dict(items=[dict(id=e.id,sequence=e.sequence,event_type=e.event_type,message=e.message,created_at=e.created_at,metadata=e.details) for e in db.scalars(stmt.order_by(Event.sequence).offset(offset).limit(limit))],total=db.scalar(select(func.count()).select_from(stmt.subquery())),offset=offset,limit=limit)

def artifact_for(db,j):
    if j.status!='completed' or j.job_type not in ('aleto_offline','partline_fixture'):raise HTTPException(409,'Результат offline-задачі ще недоступний')
    artifact=db.scalar(select(Artifact).where(Artifact.job_id==j.id))
    if not artifact or runner.adapter.sha(artifact.content)!=artifact.sha256 or artifact.sha256!=j.result_summary.get('artifact_sha256'):raise HTTPException(409,'Контрольна сума результату не збігається')
    return artifact

@router.get('/{id}/result')
def result(id:str,db:DB,who:Auth,owner:Admin):
    j=runner.owned(db,id,who.workspace_account_id)
    a=artifact_for(db,j)
    filename='partline-SYNTHETIC-result.json' if j.job_type=='partline_fixture' else 'offline-aleto-result.json'
    return Response(content=a.content,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{filename}"','X-Content-SHA256':a.sha256,'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.post('/{id}/result/import')
def prepare_import(id:str,data:Command,db:DB,who:Auth,owner:Admin):
    submit_lock(db,who.workspace_account_id)
    j=runner.owned(db,id,who.workspace_account_id,True)
    if j.job_type!='aleto_offline':raise HTTPException(409,'Ціни нових деталей PartLine не передаються в імпорт б/у каталогу')
    a=artifact_for(db,j)
    if a.catalogue_job_id:
        existing=db.get(Upload,a.catalogue_job_id)
        if not existing or existing.actor_id!=who.actor_id:raise HTTPException(409,'Підготовлений файл недоступний')
        return runner.view(j,False)
    body=json.loads(a.content)
    if body.get('synthetic') is not True or not body.get('rows'):raise HTTPException(409,'Немає валідних offline-рядків для перевірки')
    rows=[runner.ImportRow.model_validate(r).model_dump(mode='json') for r in body['rows']]
    existing=db.scalar(select(Upload).where(Upload.actor_id==who.actor_id,Upload.file_sha256==a.sha256,Upload.payload_sha256==runner.digest(rows)).order_by(Upload.created_at).limit(1))
    upload=existing or Upload(actor_id=who.actor_id,filename='OFFLINE-SYNTHETIC-Aleto.json',file_sha256=a.sha256,payload_sha256=runner.digest(rows),rows=rows,format='v2',status='uploaded',resolutions={},report={})
    db.add(upload);db.flush();a.catalogue_job_id=upload.id
    j.result_summary={**j.result_summary,'catalogue_job_id':upload.id}
    runner.event(db,j,'prepared_import','Синтетичний результат передано на окрему перевірку; каталог не змінено')
    db.commit();return runner.view(j,False)

@router.post('/{id}/{action}')
def command(id:str,action:Literal['cancel','retry'],data:Command,db:DB,who:Auth,owner:Admin):
    submit_lock(db,who.workspace_account_id)
    try:j=runner.owned(db,id,who.workspace_account_id,True);runner.command(db,j,action,data.request_key);db.commit();return runner.view(j,False)
    except IntegrityError:db.rollback();raise HTTPException(409,'Контекст уже виконується') from None
