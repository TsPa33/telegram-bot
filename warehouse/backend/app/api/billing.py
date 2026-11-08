from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.api.deps import identity,Identity
from app.api.secure_route import SecureRoute
from app.db import get_db
from app.models import Account,BillingPayment,DismantlingCredit
from app.services import billing
router=APIRouter(prefix='/api/v1/billing',route_class=SecureRoute,tags=['Warehouse billing'])
DB=Annotated[Session,Depends(get_db)]
Auth=Annotated[Identity,Depends(identity)]

def owner(who):
    if who.user.role!='DIRECTOR' or who.actor_id!=who.workspace_account_id:raise HTTPException(403,'Керування оплатою доступне власнику робочого простору')

@router.get('/status')
def status(db:DB,who:Auth):
    if who.user.role!='DIRECTOR' and not {'inventory.view','vehicles.view','dismantling.manage'} & who.permissions:raise HTTPException(403,'Недостатньо прав для перегляду лімітів')
    configured=billing.enabled();s=billing.subscription(db,who.workspace_account_id)
    employees=db.scalar(select(func.count()).select_from(Account).where(Account.workspace_account_id==who.workspace_account_id,Account.id!=who.workspace_account_id,Account.is_active.is_(True)))
    limits=billing.balance(db,who.workspace_account_id)
    plan=billing.PLANS.get(s.plan) if s else None
    used=db.scalar(select(func.coalesce(func.sum(DismantlingCredit.used),0)).where(DismantlingCredit.workspace_id==who.workspace_account_id,DismantlingCredit.source=='monthly',DismantlingCredit.expires_at==s.period_end)) if s and s.period_end else 0
    result={'enabled':configured,'sandbox':True,'demo_access':billing.exempt(who.workspace_account_id),'can_manage':who.user.role=='DIRECTOR' and who.actor_id==who.workspace_account_id,'checkout_available':False,'provider_blocker':'Контракт LiqPay subscribe та sandbox-доступ ще не підтверджені. Оплата вимкнена.',
        'subscription':{'plan':s.plan,'status':s.status if billing.active(s) else 'expired','period_end':s.period_end,'auto_renew':s.auto_renew} if s else None,
        'employees':{'used':employees if who.user.role=='DIRECTOR' or 'team.view' in who.permissions else None,'limit':plan['employees'] if plan else None},'credits':{**limits,'used':used,'included':plan['credits'] if plan else 0},'read_only':configured and not billing.exempt(who.workspace_account_id) and not billing.active(s)}
    if result['can_manage']:result.update(plans=billing.PLANS,packs={k:{'amount':v[0],'credits':v[1]} for k,v in billing.PACKS.items()})
    return result

@router.get('/payments')
def payments(db:DB,who:Auth,offset:int=0):
    owner(who)
    if offset<0:raise HTTPException(422,'Некоректна сторінка')
    q=select(BillingPayment).where(BillingPayment.workspace_id==who.workspace_account_id)
    total=db.scalar(select(func.count()).select_from(q.subquery()))
    return {'items':[{'order_id':p.id,'product':p.product,'amount':str(p.amount),'currency':p.currency,'status':p.status,'created_at':p.created_at,'confirmed_at':p.confirmed_at} for p in db.scalars(q.order_by(BillingPayment.created_at.desc(),BillingPayment.id).offset(offset).limit(25))],'total':total}

@router.post('/checkout')
def checkout(who:Auth):
    owner(who)
    raise HTTPException(503,'Sandbox checkout вимкнено до перевірки офіційного контракту LiqPay. Платіж не створено.')

@router.post('/cancel-renewal')
def cancel(who:Auth):
    owner(who)
    raise HTTPException(503,'Скасування у провайдера ще не підтверджене. Стан підписки не змінено.')

@router.post('/callback')
def callback():
    # No permissive webhook before the merchant/sandbox contract is independently verified.
    raise HTTPException(503,'LiqPay callback is disabled pending verified sandbox contract')
