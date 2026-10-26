from sqlalchemy import select,delete
from fastapi import HTTPException
from app.models import Account,Session,TeamEvent
from app.permissions import PERMISSIONS,effective,DEFAULT_EMPLOYEE,require_workspace_access

def user_info(user):
    from sqlalchemy.orm import object_session
    db=object_session(user);owner=db.get(Account,user.workspace_account_id) if db and user.workspace_account_id else user
    return {'id':user.id,'name':user.name,'email':user.email,'workspace_account_id':user.workspace_account_id or user.id,
        'workspace_name':owner.name if owner else '', 'role':user.role,'permissions':sorted(effective(user)),'is_active':user.is_active,'must_change_password':user.must_change_password,
        'created_at':user.created_at.isoformat(),'last_login_at':user.last_login_at.isoformat() if user.last_login_at else None}

def visible(db,who,id,lock=False):
    stmt=select(Account).where(Account.id==id,Account.workspace_account_id==who.workspace_account_id)
    if who.user.role!='DIRECTOR':stmt=stmt.where(Account.role=='MANAGER')
    if lock:stmt=stmt.with_for_update()
    row=db.scalar(stmt)
    if not row:raise HTTPException(404,'Працівника не знайдено')
    require_workspace_access(who,row.workspace_account_id)
    return row

def authorize_target(who,target_role,permissions):
    if target_role not in ('ADMIN','MANAGER'):raise HTTPException(403,'Роль директора не призначається через команду')
    if target_role=='MANAGER' and 'team.manage_managers' in permissions:raise HTTPException(422,'Менеджер не може керувати ролями')
    if set(permissions)-PERMISSIONS.keys():raise HTTPException(422,'Невідомий дозвіл')
    if who.user.role!='DIRECTOR':
        if who.user.role!='ADMIN' or target_role!='MANAGER' or 'team.manage_managers' not in who.permissions:
            raise HTTPException(403,'Адміністратор може керувати лише менеджерами')
        if not set(permissions)<=who.permissions:raise HTTPException(403,'Не можна делегувати права, яких немає у вас')

def event(db,who,target,type,data):
    db.add(TeamEvent(workspace_account_id=who.workspace_account_id,actor_id=who.actor_id,target_id=target.id,type=type,data=data))

def revoke_sessions(db,id):db.execute(delete(Session).where(Session.account_id==id))


def creation_enabled():
    import os
    # Fail closed in every environment; activation is a separate release step.
    return os.getenv('WAREHOUSE_TEAM_CREATION_ENABLED','false').lower()=='true'


def require_creation_enabled():
    if not creation_enabled():raise HTTPException(403,'Створення співробітників ще не ввімкнено')
