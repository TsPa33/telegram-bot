"""Authenticated shared reading and independently gated platform administration."""
import hashlib
import json
from typing import Annotated,Literal
from urllib.parse import unquote
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select,func,and_
from sqlalchemy.orm import Session,defer
from starlette.concurrency import run_in_threadpool
from app.api.secure_route import SecureRoute
from app.api.deps import identity,Identity
from app.db import get_db
from app.models.catalogue import CatalogueJob as Job,CatalogueEntity as Entity,CatalogueOffer as Offer,CatalogueSource as Source,CataloguePrice as Price,CataloguePath as Path,CatalogueOperation as Operation
from app.services.catalogue_format import parse_upload,digest,MAX_UPLOAD
from app.services.catalogue_import import require_admin,platform_admin
from app.services.aleto_import import identity as normalize_name
from app.services.catalogue_jobs import enqueue,operation_summary

router=APIRouter(route_class=SecureRoute,prefix='/api/v1/catalogue',tags=['Universal Catalogue v2'])
DB=Annotated[Session,Depends(get_db)]
Auth=Annotated[Identity,Depends(identity)]


def admin(db:DB,who:Auth):
    return require_admin(db,who)
Admin=Annotated[object,Depends(admin)]


def summary(job,detail=False,operation=None):
    report=job.report if detail else {k:v for k,v in job.report.items() if k not in ('issues','suggestions')}
    return dict(id=job.id,filename=job.filename,file_sha256=job.file_sha256,payload_sha256=job.payload_sha256,
                format=job.format,status=job.status,created_at=job.created_at,applied_at=job.applied_at,
                operation=operation_summary(operation,include_command=detail) if operation else None,
                preview_token=job.preview_token,report=report,**({'resolutions':job.resolutions} if detail else {}))


@router.get('/capabilities')
def capabilities(who:Auth):
    return {'platform_admin':platform_admin(who.user)}


def store_upload(db,actor,raw,filename):
    try:rows,format=parse_upload(raw,filename)
    except (ValueError,sqlite3.Error,TypeError) as exc:
        # Persist rejection metadata, not the untrusted body or validation input.
        job=Job(actor_id=actor.id,filename=filename,file_sha256=hashlib.sha256(raw).hexdigest(),
                payload_sha256=digest([]),rows=[],format='rejected',status='failed',report={'error':str(exc)[:500]})
        db.add(job);db.commit()
        return JSONResponse(status_code=422,content={'detail':'Файл відхилено: '+str(exc)[:500],'job_id':job.id})
    if len(json.dumps(rows,ensure_ascii=False).encode())>64*1024*1024:
        raise HTTPException(413,'Перевірені дані перевищують 64 MiB')
    job=Job(actor_id=actor.id,filename=filename,file_sha256=hashlib.sha256(raw).hexdigest(),
            payload_sha256=digest(rows),rows=rows,format=format,status='uploaded')
    db.add(job);db.commit()
    return summary(job,True)


@router.post('/admin/jobs',status_code=201)
async def upload(request:Request,db:DB,owner:Admin):
    # Auth+CSRF+platform role are checked BEFORE reading a bounded binary stream.
    filename=unquote(request.headers.get('X-Catalogue-Filename','catalogue'))
    if not filename or len(filename)>200 or any(ord(c)<32 for c in filename):raise HTTPException(422,'Некоректна назва файла')
    filename=filename.replace('\\','/').split('/')[-1]
    if not filename:raise HTTPException(422,'Некоректна назва файла')
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>MAX_UPLOAD:raise HTTPException(413,'Файл перевищує 16 MiB')
        data.extend(chunk)
    return await run_in_threadpool(store_upload,db,owner,bytes(data),filename)


@router.get('/admin/jobs')
def history(db:DB,owner:Admin,offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100)):
    jobs=list(db.scalars(select(Job).options(defer(Job.rows),defer(Job.resolutions)).order_by(Job.created_at.desc(),Job.id).offset(offset).limit(limit)))
    operations={op.job_id:op for op in db.scalars(select(Operation).where(Operation.job_id.in_([j.id for j in jobs]))
        .distinct(Operation.job_id).order_by(Operation.job_id,Operation.created_at.desc(),Operation.id.desc()))} if jobs else {}
    return {'items':[summary(j,operation=operations.get(j.id)) for j in jobs],
            'total':db.scalar(select(func.count()).select_from(Job)),'offset':offset,'limit':limit}


@router.get('/admin/jobs/{id}')
def job(id:str,db:DB,owner:Admin):
    # Read operation first: observing terminal status must also observe the
    # job/catalogue commit. Reading job first can return a stale plan with done.
    operation=db.scalar(select(Operation).where(Operation.job_id==id).order_by(Operation.created_at.desc(),Operation.id.desc()).limit(1))
    row=db.scalar(select(Job).where(Job.id==id).options(defer(Job.rows)))
    if not row:raise HTTPException(404,'Import job не знайдено')
    return summary(row,True,operation)


class Resolution(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:str=Field(pattern=r'^(target|create_name|skip|keep_existing|accept_incoming)$')
    target_id:str|None=Field(default=None,max_length=36)
    name:str|None=Field(default=None,max_length=1000)


class PreviewInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    resolutions:dict[str,Resolution]=Field(default_factory=dict,max_length=10000)


@router.post('/admin/jobs/{id}/preview',status_code=202)
def preview_job(id:str,data:PreviewInput,db:DB,owner:Admin,who:Auth):
    operation=enqueue(db,id,'preview',{'resolutions':{k:v.model_dump(exclude_none=True) for k,v in data.resolutions.items()}},who)
    db.commit()
    db.refresh(operation) # Snapshot status before reading the corresponding job.
    row=db.scalar(select(Job).where(Job.id==id).options(defer(Job.rows)))
    return summary(row,True,operation)


class ApplyInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    preview_token:str=Field(pattern=r'^[a-f0-9]{64}$')
    confirm:bool=Field(strict=True)


@router.post('/admin/jobs/{id}/apply',status_code=202)
def apply_job(id:str,data:ApplyInput,db:DB,owner:Admin,who:Auth):
    if data.confirm is not True:raise HTTPException(422,'Потрібне явне підтвердження')
    operation=enqueue(db,id,'apply',{'preview_token':data.preview_token},who)
    db.commit()
    db.refresh(operation) # Snapshot status before reading the corresponding job.
    row=db.scalar(select(Job).where(Job.id==id).options(defer(Job.rows)))
    return summary(row,True,operation)


@router.get('/admin/entities')
def candidates(db:DB,owner:Admin,kind:str=Query(pattern=r'^(manufacturer|model|category|subcategory|part_type)$'),
               parent_id:str|None=Query(None,max_length=36),q:str=Query('',max_length=200)):
    stmt=select(Entity).where(Entity.kind==kind,Entity.parent_id==parent_id)
    if q:stmt=stmt.where(Entity.normalized_name.contains(normalize_name(q),autoescape=True))
    return {'items':[dict(id=e.id,name=e.name,details=e.details) for e in db.scalars(stmt.order_by(Entity.name).limit(50))]}


@router.get('/entities')
def entities(db:DB,who:Auth,kind:str=Query(pattern=r'^(manufacturer|model|category|subcategory|part_type)$'),
             parent_id:str|None=Query(None,max_length=36),q:str=Query('',max_length=200),limit:int=Query(100,ge=1,le=200)):
    stmt=select(Entity).where(Entity.kind==kind)
    if parent_id:stmt=stmt.where(Entity.parent_id==parent_id)
    if q:
        from app.services.aleto_import import identity as norm
        stmt=stmt.where(Entity.normalized_name.contains(norm(q),autoescape=True))
    rows=list(db.scalars(stmt.order_by(Entity.name,Entity.id).limit(limit)))
    parent_ids={e.parent_id for e in rows if e.parent_id}
    parents={e.id:e.name for e in db.scalars(select(Entity).where(Entity.id.in_(parent_ids)))} if parent_ids else {}
    return {'items':[dict(id=e.id,kind=e.kind,name=e.name,parent_id=e.parent_id,parent_name=parents.get(e.parent_id),details=e.details) for e in rows]}


@router.get('')
def read_catalogue(db:DB,who:Auth,model_id:str|None=Query(None,max_length=36),category_id:str|None=Query(None,max_length=36),
                   subcategory_id:str|None=Query(None,max_length=36),q:str=Query('',max_length=200),
                   offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
    from sqlalchemy.orm import aliased
    part,sub=aliased(Entity),aliased(Entity)
    path=select(Path.offer_id)
    if model_id:path=path.where(Path.model_id==model_id)
    if category_id or subcategory_id:
        path=path.join(part,Path.part_type_id==part.id).join(sub,part.parent_id==sub.id)
        if subcategory_id:path=path.where(sub.id==subcategory_id)
        if category_id:path=path.where(sub.parent_id==category_id)
    stmt=select(Offer)
    if model_id or category_id or subcategory_id:stmt=stmt.where(Offer.id.in_(path))
    if q:
        stmt=stmt.where((Offer.source_article==q)|(Offer.properties['oem'].as_string()==q)|
                        Offer.properties['part_name'].as_string().ilike('%'+q.replace('\\','\\\\').replace('%',r'\%').replace('_',r'\_')+'%',escape='\\'))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=db.execute(stmt.add_columns(Source,Price).join(Source,Offer.source_id==Source.id).join(Price,and_(Price.offer_id==Offer.id,Price.observed_at==Offer.observed_at)).order_by(Source.name,Offer.source_article).offset(offset).limit(limit))
    return {'items':[dict(**{**o.properties,'id':o.id,'source':s.name,'source_article':o.source_article,
                          'price_uah':str(p.price_uah) if p.price_uah is not None else None,'price_usd':str(p.price_usd) if p.price_usd is not None else None,'observed_at':p.observed_at,'source_url':p.source_url}) for o,s,p in rows],
            'total':total,'offset':offset,'limit':limit,'year_compatibility':'unverified','price_label':'Ринкова пропозиція джерела — не ваша ціна продажу'}


@router.get('/admin/overview')
def admin_overview(db:DB,owner:Admin):
    from app.services.parser_admin import overview
    from sqlalchemy.exc import DBAPIError
    try:return overview(db)
    except DBAPIError:
        db.rollback()
        raise HTTPException(503,'Показники каталогу тимчасово недоступні. Спробуйте пізніше.') from None


class ParserParameters(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    source:Literal['aleto','avtopro','file']
    manufacturer:str=Field(default='',max_length=100)
    model:str=Field(default='',max_length=100)
    year_from:int|None=Field(default=None,ge=1886,le=2100,strict=True)
    year_to:int|None=Field(default=None,ge=1886,le=2100,strict=True)
    collect:list[Literal['names','oem','prices','categories']]=Field(min_length=1,max_length=4)


@router.post('/admin/parser/validate')
def validate_parser_parameters(data:ParserParameters,db:DB,owner:Admin):
    from app.services.auth import throttle
    throttle(('parser-parameters',owner.id))
    if data.source!='file' and (not data.manufacturer or not data.model):raise HTTPException(422,'Вкажіть марку та модель')
    if data.year_from and data.year_to and data.year_from>data.year_to:raise HTTPException(422,'Початковий рік не може перевищувати кінцевий')
    if len(set(data.collect))!=len(data.collect):raise HTTPException(422,'Параметри збору не повинні повторюватися')
    return dict(valid=True,runnable=False,parameters=data.model_dump(),message='Параметри перевірено. Сумісність із джерелом не підтверджена; онлайн-збір не підключено. Для дозволеного експорту використайте імпорт файлу.')
