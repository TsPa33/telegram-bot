"""Stage 1: owner-only normalization governance and read-only candidate APIs."""
from typing import Literal
from fastapi import APIRouter,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select,text,func
from sqlalchemy.dialects.postgresql import insert
from app.api.catalogue import DB,Auth,Admin
from app.api.secure_route import SecureRoute
from app.models import Vehicle
from app.models.canonical import CanonicalType as Type,CanonicalAlias as Alias,CanonicalFitment as Fitment,CanonicalMapping as Mapping,CanonicalState as State,CanonicalRun as Run
from app.services.catalogue_import import LOCK
from app.services.catalogue_format import digest
from app.services.canonical_rules import type_record,norm,sid,TYPES,LEX,surface
from app.services.canonical_terms import alias_series
from app.schemas.canonical import SourceConditions,GroupRuleInput,GroupApprovalInput
from app.services.canonical_catalogue import global_inputs
from app.services.canonical_candidates import candidates
from app.services.canonical_jobs import enqueue,summary
from app.services.inventory import owned
router=APIRouter(route_class=SecureRoute,tags=['Canonical dismantling reference v3'])

def admin_lock(db):
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK}):
        raise HTTPException(409,'Імпорт або нормалізація виконується; повторіть дію після завершення')

class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class RunInput(Strict):
    mode:Literal['preview','publish']='preview'
    preview_id:str|None=Field(default=None,max_length=36)
    token:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    confirm:bool=Field(default=False,strict=True)

@router.post('/api/v1/catalogue/admin/canonical/runs',status_code=202)
def start(data:RunInput,db:DB,owner:Admin,who:Auth):
    if data.mode=='publish' and (not data.confirm or not data.preview_id or not data.token):raise HTTPException(422,'Потрібне явне підтвердження та token завершеної перевірки')
    run=enqueue(db,who,data.mode,data.preview_id,data.token);db.commit();return summary(run)

@router.get('/api/v1/catalogue/admin/canonical/runs/{id}')
def run_status(id:str,db:DB,owner:Admin):
    run=db.get(Run,id)
    if not run:raise HTTPException(404,'Перевірку не знайдено')
    return summary(run)

@router.get('/api/v1/catalogue/admin/canonical/review')
def review(db:DB,owner:Admin,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
    state=db.get(State,1);sha=state.snapshot_sha if state else None
    stmt=select(Mapping).where(Mapping.snapshot_sha==sha,Mapping.quality.in_(['review','unprocessed']))
    return {'items':[dict(source_key=r.source_key,source_sha=r.source_sha,quality=r.quality,evidence=r.evidence) for r in db.scalars(stmt.order_by(Mapping.source_key).offset(offset).limit(limit))],
        'total':db.scalar(select(func.count()).select_from(stmt.subquery()))}

class TypeInput(Strict):
    name:str=Field(min_length=1,max_length=200)
    category:str=Field(min_length=1,max_length=200)
    subcategory:str=Field(min_length=1,max_length=200)
    evidence:str=Field(min_length=5,max_length=2000)
    @model_validator(mode='after')
    def labels(self):
        if any(ord(c)<32 or c in 'ыэёъЫЭЁЪ' for s in (self.name,self.category,self.subcategory) for c in s):raise ValueError('Потрібні перевірені українські назви без control characters')
        return self

@router.post('/api/v1/catalogue/admin/canonical/types',status_code=201)
def create_type(data:TypeInput,db:DB,owner:Admin):
    admin_lock(db)
    from app.models.catalogue import CatalogueEntity
    brands={'volvo','bmw','audi'}|{norm(n) for n in db.scalars(select(CatalogueEntity.name).where(CatalogueEntity.kind=='manufacturer'))}
    if any(brand and (' '+brand+' ') in (' '+norm(data.name)+' ') for brand in brands):raise HTTPException(422,'Марка не є частиною канонічної функції; використайте варіант або застосовність')
    known={r['type_id'] for r in LEX.get(surface({'title':data.name})['phrase'],[])}
    row=TYPES[next(iter(known))] if len(known)==1 else type_record(data.name,data.category,data.subcategory,{'actor_id':owner.id,'evidence':data.evidence})
    db.execute(insert(Type).values(**row).on_conflict_do_nothing(index_elements=['id']));db.commit();return {'id':row['id']}

class Installation(Strict):
    side:Literal['left','right','unknown']='unknown'
    position:Literal['front','rear','unknown']='unknown'
    mount:list[Literal['upper','lower','inner','outer']]=Field(default_factory=list,max_length=4)
    @model_validator(mode='after')
    def consistent(self):
        if any(a in self.mount and b in self.mount for a,b in [('upper','lower'),('inner','outer')]):raise ValueError('Суперечлива позиція')
        self.mount=sorted(set(self.mount))
        return self
class AliasInput(Strict):
    type_id:str|None=Field(default=None,max_length=36)
    source_key:str|None=Field(default=None,max_length=200)
    source_sha:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    phrase:str=Field(default='',max_length=1000)
    category:str=Field(default='',max_length=200)
    subcategory:str=Field(default='',max_length=200)
    manufacturer:str=Field(default='',max_length=100)
    model:str=Field(default='',max_length=100)
    installation:Installation|None=None
    conditions:SourceConditions|None=None
    enabled:bool=Field(default=True,strict=True)
    expected_revision:int=Field(default=0,ge=0)
    evidence:str=Field(min_length=5,max_length=2000)
    @model_validator(mode='after')
    def match_scope(self):
        if self.enabled and not self.type_id:raise ValueError('Потрібен канонічний тип')
        if self.source_key:
            if not self.source_sha or self.phrase:raise ValueError('Потрібен точний SHA джерела; phrase не поєднується з source_key')
        elif not self.phrase or not self.category or not self.subcategory:raise ValueError('Потрібен повний phrase та явний контекст категорії/підкатегорії')
        return self

@router.post('/api/v1/catalogue/admin/canonical/aliases',status_code=201)
def approve(data:AliasInput,db:DB,owner:Admin):
    admin_lock(db)
    if data.type_id and not db.get(Type,data.type_id):raise HTTPException(404,'Канонічний тип не знайдено')
    if data.source_key and not any(r['key']==data.source_key and r['sha']==data.source_sha for r in global_inputs(db)):raise HTTPException(409,'Джерело змінилося або не належить глобальному каталогу')
    match={k:getattr(data,k) for k in ('source_key','source_sha')} if data.source_key else {k:norm(getattr(data,k)) for k in ('phrase','category','subcategory','manufacturer','model')}
    conditions=data.conditions.model_dump(exclude_none=True) if data.conditions else {}
    if conditions:match['conditions']=conditions
    key=alias_series(match)
    previous=db.scalar(select(Alias).where(Alias.series_key==key).order_by(Alias.revision.desc()).limit(1))
    if (previous.revision if previous else 0)!=data.expected_revision:raise HTTPException(409,'Рішення змінено; перечитайте актуальну revision')
    criteria={**match,**({'installation':data.installation.model_dump()} if data.installation else {})}
    row=Alias(series_key=key,revision=data.expected_revision+1,type_id=data.type_id,criteria=criteria,enabled=data.enabled,evidence=data.evidence,actor_id=owner.id)
    db.add(row);db.commit();return {'id':row.id,'revision':row.revision,'published':False}

@router.get('/api/v1/catalogue/admin/canonical/aliases')
def alias_history(db:DB,owner:Admin,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
    return {'items':[{k:getattr(a,k) for k in ('id','series_key','revision','enabled','type_id','criteria','evidence','actor_id','created_at')} for a in db.scalars(select(Alias).order_by(Alias.created_at.desc(),Alias.id).offset(offset).limit(limit))],
        'total':db.scalar(select(func.count()).select_from(Alias))}

class FitmentInput(Strict):
    variant_id:str=Field(max_length=36)
    manufacturer:str=Field(min_length=1,max_length=100)
    model:str=Field(min_length=1,max_length=100)
    generation:str=Field(default='',max_length=100)
    year_from:int|None=Field(default=None,ge=1886,le=2100,strict=True)
    year_to:int|None=Field(default=None,ge=1886,le=2100,strict=True)
    engine:str=Field(default='',max_length=100)
    fuel_type:str=Field(default='',max_length=50)
    transmission:str=Field(default='',max_length=50)
    engine_code:str=Field(default='',max_length=100)
    powertrain:Literal['','petrol','diesel','HEV','PHEV','BEV']=''
    drive:Literal['','FWD','RWD','AWD','4WD']=''
    body_type:str=Field(default='',max_length=100)
    options:list[str]=Field(default_factory=list,max_length=100)
    status:Literal['confirmed','incompatible']
    evidence:str=Field(min_length=5,max_length=2000)
    @model_validator(mode='after')
    def years(self):
        if self.year_from and self.year_to and self.year_from>self.year_to:raise ValueError('Неправильний діапазон років')
        return self

@router.post('/api/v1/catalogue/admin/canonical/fitments',status_code=201)
def fitment(data:FitmentInput,db:DB,owner:Admin):
    from app.models.canonical import CanonicalVariant
    if not db.get(CanonicalVariant,data.variant_id):raise HTTPException(404,'Варіант не знайдено')
    admin_lock(db)
    criteria=data.model_dump(exclude={'variant_id','status','evidence'})
    rid=sid('fitment',data.variant_id,criteria,data.status,data.evidence,owner.id)
    db.execute(insert(Fitment).values(id=rid,variant_id=data.variant_id,criteria=criteria,status=data.status,evidence=data.evidence,actor_id=owner.id).on_conflict_do_nothing(index_elements=['id']));db.commit();return {'id':rid}

@router.get('/api/v1/catalogue/canonical/candidates')
def by_model(db:DB,who:Auth,manufacturer:str=Query(min_length=1,max_length=100),model:str=Query(min_length=1,max_length=100),
    generation:str=Query('',max_length=100),year:int|None=Query(None,ge=1886,le=2100),engine:str=Query('',max_length=100),fuel_type:str=Query('',max_length=50),transmission:str=Query('',max_length=50),offset:int=Query(0,ge=0),limit:int=Query(500,ge=1,le=500)):
    return candidates(db,dict(manufacturer=manufacturer,model=model,generation=generation,year=year,engine=engine,fuel_type=fuel_type,transmission=transmission),offset=offset,limit=limit)

@router.get('/api/v1/vehicles/{id}/dismantling/candidates')
def by_vehicle(id:str,db:DB,who:Auth,offset:int=Query(0,ge=0),limit:int=Query(500,ge=1,le=500)):
    vehicle=owned(db,Vehicle,id,who.workspace_account_id)
    query={k:getattr(vehicle,k) for k in ('manufacturer','model','generation','year','engine','fuel_type','transmission')}
    from app.services.vehicle_configuration import latest
    config=latest(db,vehicle,who.workspace_account_id)
    if config and config['status']=='confirmed':
        query.update({k:v for k,v in config['values'].items() if v is not None and k not in ('vin','engine_label','options_complete')})
        if config['values'].get('engine_code'):query['engine']=config['values']['engine_code']
    else:config=None
    return candidates(db,query,who.workspace_account_id,offset,limit,configuration=config)

@router.get('/api/v1/catalogue/canonical/sources')
def sources(db:DB,who:Auth,placement_id:str=Query(max_length=36),offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
    state=db.get(State,1);sha=state.snapshot_sha if state else None
    stmt=select(Mapping).where(Mapping.snapshot_sha==sha,Mapping.placement_id==placement_id)
    return {'snapshot_sha':sha,'items':[dict(source_key=r.source_key,source_sha=r.source_sha,quality=r.quality,published_evidence=r.evidence) for r in db.scalars(stmt.order_by(Mapping.source_key).offset(offset).limit(limit))],
        'total':db.scalar(select(func.count()).select_from(stmt.subquery()))}


@router.get('/api/v1/catalogue/admin/canonical/groups')
def unresolved_groups(db:DB,owner:Admin,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
    from app.services.canonical_review import groups
    return groups(db,offset,limit)

@router.post('/api/v1/catalogue/admin/canonical/rules/preview',status_code=202)
def preview_rule(data:GroupRuleInput,db:DB,owner:Admin,who:Auth):
    draft=data.model_dump();draft['conditions']=data.conditions.model_dump(exclude_none=True)
    run=enqueue(db,who,'preview',request={'kind':'rule-preview-request','draft':draft});db.commit();return summary(run)

@router.post('/api/v1/catalogue/admin/canonical/rules/approve',status_code=202)
def approve_group(data:GroupApprovalInput,db:DB,owner:Admin,who:Auth):
    if not data.confirm:raise HTTPException(422,'Потрібне явне підтвердження групового правила')
    run=enqueue(db,who,'publish',data.preview_id,data.token,request={'kind':'rule-approve-request','confirm':True});db.commit();return summary(run)

@router.get('/api/v1/catalogue/admin/canonical/diagnostics')
def diagnose(db:DB,owner:Admin,who:Auth,vehicle_id:str|None=Query(None,max_length=36)):
    from app.services.canonical_diagnostics import diagnostics
    vehicle=owned(db,Vehicle,vehicle_id,who.workspace_account_id) if vehicle_id else None
    return diagnostics(db,vehicle)

@router.get('/api/v1/catalogue/admin/canonical/types')
def available_types(db:DB,owner:Admin):
    rows={**TYPES,**{t.id:{k:getattr(t,k) for k in ('id','name','category','subcategory')} for t in db.scalars(select(Type))}}
    return {'items':sorted([dict(id=r['id'],name=r['name'],category=r['category'],subcategory=r['subcategory']) for r in rows.values()],key=lambda r:(r['category'],r['name']))}
