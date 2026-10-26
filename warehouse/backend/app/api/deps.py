import hmac
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from app.db import get_db
from app.models import Account, Session, now
from app.services.auth import digest
from app.permissions import effective,require_permission,route_permissions,check_fields

@dataclass
class Identity:
    user: Account
    session: Session
    workspace_account_id: str
    actor_id: str
    permissions: frozenset

async def permission_body(request:Request):
    # Only body parsing is async; blocking SQL/row locks run in the worker pool.
    body={}
    if request.headers.get('content-type','').startswith('application/json'):
        body=await request.json()
        if isinstance(body,dict):body=dict(body)
        if not isinstance(body,dict):body={}
    body['_route_action']=request.path_params.get('action')
    return body


def identity(request:Request,db:DBSession=Depends(get_db),body:dict=Depends(permission_body)):
    token=request.cookies.get('warehouse_session','')
    session=db.get(Session,digest(token)) if token else None
    if not session or session.expires_at<=now():raise HTTPException(401,'Увійдіть до облікового запису')
    user=db.get(Account,session.account_id)
    if not user or not user.is_active:raise HTTPException(401,'Доступ заблоковано')
    if request.method not in ('GET','HEAD','OPTIONS') and user.role!='DIRECTOR':
        user=db.scalar(select(Account).where(Account.id==user.id).with_for_update(read=True).execution_options(populate_existing=True))
        if not user.is_active:raise HTTPException(401,'Доступ заблоковано')
        # A reset/logout may have revoked the session while this request waited
        # for the actor row lock. Do not trust the earlier identity-map entry.
        session=db.scalar(select(Session).where(Session.token_hash==digest(token)).execution_options(populate_existing=True))
        if not session or session.expires_at<=now():raise HTTPException(401,'Сесію відкликано')
    workspace=user.workspace_account_id or user.id
    owner=db.get(Account,workspace)
    if not owner or owner.role!='DIRECTOR' or not owner.is_active:raise HTTPException(401,'Робочий простір недоступний')
    if request.method not in ('GET','HEAD','OPTIONS'):
        csrf=request.headers.get('X-CSRF-Token','')
        if not csrf or not hmac.compare_digest(digest(csrf),session.csrf_hash):raise HTTPException(403,'Недійсний CSRF-токен. Оновіть сторінку')
    who=Identity(user,session,workspace,user.id,effective(user))
    path=request.scope['route'].path
    if user.must_change_password and path not in ('/api/v1/auth/me','/api/v1/auth/logout','/api/v1/auth/password'):
        raise HTTPException(403,'Спочатку змініть тимчасовий пароль')
    require_permission(who,*route_permissions(request.method,path,body));check_fields(who,path,body)
    db.info.update(actor_id=user.id,workspace_account_id=workspace,permissions=who.permissions)
    request.state.identity=who
    return who
