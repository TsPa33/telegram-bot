from typing import Literal
from fastapi import APIRouter,HTTPException,Query
from pydantic import Field,ConfigDict,field_validator
from sqlalchemy import select,func,text
from app.api.secure_route import SecureRoute
from app.api.routes import DB,Auth
from app.models import Account,TeamEvent,Session,StockRequest,OrderRequest
from app.schemas import Credentials,Input
from app.permissions import GROUPS,PERMISSIONS,DEFAULT_EMPLOYEE,require_permission,require_director
from app.services import auth,team

router=APIRouter(route_class=SecureRoute,prefix='/api/v1')
REVISION='b94f62d18e07'
class CreateEmployee(Credentials):
    name:str=Field(min_length=1,max_length=120)
    role:Literal['ADMIN','MANAGER']='MANAGER'
    permissions:list[str]=Field(default_factory=lambda:list(DEFAULT_EMPLOYEE),max_length=100)
class UpdateEmployee(Input):
    name:str=Field(min_length=1,max_length=120)
    role:Literal['ADMIN','MANAGER']
    permissions:list[str]=Field(max_length=100)
    is_active:bool
class ResetPassword(Input):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)
    @field_validator('password')
    @classmethod
    def exact_password(cls,value):
        if value!=value.strip():raise ValueError('Пароль не повинен починатися чи закінчуватися пробілами')
        return value
    password:str=Field(min_length=12,max_length=128)
class ChangePassword(ResetPassword):
    current_password:str=Field(min_length=12,max_length=128)

@router.get('/team/readiness')
def readiness(db:DB,who:Auth):
    from app.staging import migration_heads
    heads=frozenset(db.execute(text('SELECT version_num FROM alembic_version')).scalars())
    if heads!=migration_heads() or REVISION not in heads:raise HTTPException(503,'Team schema is not ready')
    db.execute(select(StockRequest.actor_id).limit(0));db.execute(select(OrderRequest.actor_id).limit(0))
    if not db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='accounts'::regclass AND conname='ck_account_workspace_role' AND convalidated)")):raise HTTPException(503,'Team role constraints are not ready')
    if not db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='team_events'::regclass AND tgname='immutable_team_events' AND tgenabled='O')")):raise HTTPException(503,'Team security audit is not immutable')
    db.execute(select(Account.workspace_account_id,Account.permissions,Account.is_active).limit(0));db.execute(select(TeamEvent.id).limit(0))
    return {'status':'ready','contract_version':9,'required_revision':REVISION,'database_revisions':sorted(heads),
        'employee_creation_enabled':team.creation_enabled(),'features':['workspace_actor_separation','server_permissions','live_session_revocation','financial_redaction','actor_bound_replay']}

@router.get('/team/permissions')
def permissions(who:Auth):return {'groups':GROUPS,'grantable':sorted(who.permissions)}

@router.get('/team')
def listing(db:DB,who:Auth,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
    stmt=select(Account).where((Account.workspace_account_id==who.workspace_account_id)|(Account.id==who.workspace_account_id))
    if who.user.role!='DIRECTOR':stmt=stmt.where(Account.role=='MANAGER')
    return {'items':[team.user_info(u) for u in db.scalars(stmt.order_by(Account.created_at,Account.id).offset(offset).limit(limit))],
        'total':db.scalar(select(func.count()).select_from(stmt.subquery())),'offset':offset,'limit':limit}

@router.get('/team/summary')
def summary(db:DB,who:Auth):
    # Same visibility as the directory; aggregates never depend on pagination.
    scope=(Account.workspace_account_id==who.workspace_account_id)|(Account.id==who.workspace_account_id)
    stmt=select(Account.role,Account.is_active,func.count()).where(scope)
    if who.user.role!='DIRECTOR':stmt=stmt.where(Account.role=='MANAGER')
    rows=db.execute(stmt.group_by(Account.role,Account.is_active)).all()
    roles={role:0 for role in ('DIRECTOR','ADMIN','MANAGER')}
    active=blocked=0
    for role,is_active,count in rows:
        roles[role]+=count
        if is_active:active+=count
        else:blocked+=count
    return {'total':active+blocked,'active':active,'blocked':blocked,'by_role':roles,
            'scope':'workspace' if who.user.role=='DIRECTOR' else 'visible_managers'}

@router.post('/team',status_code=201)
def create(data:CreateEmployee,db:DB,who:Auth):
    team.require_creation_enabled()
    team.authorize_target(who,data.role,data.permissions)
    row=Account(name=data.name,email=data.email,password_hash=auth.hasher.hash(data.password),workspace_account_id=who.workspace_account_id,role=data.role,permissions=sorted(set(data.permissions)),must_change_password=True)
    db.add(row);db.flush();team.event(db,who,row,'employee_created',{'role':row.role,'permissions':row.permissions});db.commit()
    return team.user_info(row)

@router.patch('/team/{id}')
def update(id:str,data:UpdateEmployee,db:DB,who:Auth):
    row=team.visible(db,who,id,lock=True)
    team.authorize_target(who,row.role,[])
    if set(data.permissions)-PERMISSIONS.keys():raise HTTPException(422,'Невідомий дозвіл')
    # Reactivation restores effective access, so all retained permissions are grants.
    grants=data.permissions if who.user.role=='DIRECTOR' or (data.is_active and not row.is_active) else sorted(set(data.permissions)-set(row.permissions))
    team.authorize_target(who,data.role,grants)
    before={'name':row.name,'role':row.role,'permissions':row.permissions,'is_active':row.is_active}
    row.name=data.name;row.role=data.role;row.permissions=sorted(set(data.permissions));row.is_active=data.is_active
    if not row.is_active:team.revoke_sessions(db,row.id)
    team.event(db,who,row,'employee_updated',{'before':before,'after':{'name':row.name,'role':row.role,'permissions':row.permissions,'is_active':row.is_active}});db.commit();return team.user_info(row)

@router.post('/team/{id}/reset-password')
def reset(id:str,data:ResetPassword,db:DB,who:Auth):
    row=team.visible(db,who,id,lock=True);team.authorize_target(who,row.role,row.permissions)
    row.password_hash=auth.hasher.hash(data.password);row.must_change_password=True;team.revoke_sessions(db,row.id)
    team.event(db,who,row,'access_reset',{});db.commit();return {'status':'reset'}

@router.post('/auth/password')
def password(data:ChangePassword,db:DB,who:Auth):
    # Identity and CSRF were checked before current-password verification.
    auth.throttle(('password-change',who.actor_id))
    auth.authenticate(db,who.user.email,data.current_password)
    if data.current_password==data.password:raise HTTPException(422,'Виберіть інший пароль')
    who.user.password_hash=auth.hasher.hash(data.password);who.user.must_change_password=False
    team.revoke_sessions(db,who.actor_id);team.event(db,who,who.user,'password_changed',{});db.commit()
    return {'status':'password_changed','login_required':True}

@router.get('/team/events')
def events(db:DB,who:Auth,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
    require_director(who)
    return {'items':[{'id':e.id,'actor_id':e.actor_id,'target_id':e.target_id,'type':e.type,'data':e.data,'created_at':e.created_at.isoformat()} for e in db.scalars(select(TeamEvent).where(TeamEvent.workspace_account_id==who.workspace_account_id).order_by(TeamEvent.created_at.desc(),TeamEvent.id).offset(offset).limit(limit))],'total':db.scalar(select(func.count()).select_from(TeamEvent).where(TeamEvent.workspace_account_id==who.workspace_account_id)),'offset':offset,'limit':limit}
