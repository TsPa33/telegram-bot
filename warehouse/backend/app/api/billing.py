from pydantic import BaseModel,ConfigDict,Field
from typing import Annotated,Any
from fastapi import APIRouter,Depends,HTTPException,Body
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.api.deps import identity,Identity
from app.api.secure_route import SecureRoute
from app.db import get_db
from app.models import Account,BillingPayment,DismantlingCredit
from app.models.entitlements import EntitlementWorkspace
from app.services import billing
from app.services import global_billing as global_finance
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
    if entitlements.enabled():result['entitlements_available']=True
    return result

@router.get('/payments')
def payments(db:DB,who:Auth,offset:int=0):
    owner(who)
    if offset<0:raise HTTPException(422,'Некоректна сторінка')
    q=select(BillingPayment).where(BillingPayment.workspace_id==who.workspace_account_id)
    total=db.scalar(select(func.count()).select_from(q.subquery()))
    return {'items':[{'order_id':p.id,'product':p.product,'amount':str(p.amount),'currency':p.currency,'status':p.status,'created_at':p.created_at,'confirmed_at':p.confirmed_at} for p in db.scalars(q.order_by(BillingPayment.created_at.desc(),BillingPayment.id).offset(offset).limit(25))],'total':total}

class GlobalCheckout(BaseModel):
    model_config=ConfigDict(extra='forbid')
    invoice_id:str=Field(min_length=36,max_length=36)

@router.post('/checkout')
def checkout(db:DB,who:Auth,body:Any=Body(default=None)):
    owner(who)
    if not global_finance.enabled():raise HTTPException(503,'Sandbox checkout вимкнено до перевірки офіційного контракту LiqPay. Платіж не створено.')
    try:data=GlobalCheckout.model_validate(body)
    except ValueError:raise HTTPException(422,'Потрібний чинний рахунок') from None
    p=global_finance.binding(db,who)
    return global_finance.request(who,'POST','/v1/checkout',{'invoice_id':data.invoice_id},binding=p)

@router.post('/cancel-renewal')
def cancel(who:Auth):
    owner(who)
    raise HTTPException(503,'Скасування у провайдера ще не підтверджене. Стан підписки не змінено.')

@router.post('/callback')
def callback():
    # No permissive webhook before the merchant/sandbox contract is independently verified.
    raise HTTPException(503,'LiqPay callback is disabled pending verified sandbox contract')

# Phase 2 routes are separate from disabled legacy checkout/credits.
from app.services import entitlements
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal

class TrialInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    plan:Literal['standard','premium']

class QuoteInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    pack:Literal['pack_1','pack_5','pack_10']

class ReturnInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sale_id:str=Field(min_length=36,max_length=36)
    quantity:int=Field(strict=True,gt=0,le=1000000)
    request_key:str=Field(min_length=36,max_length=36)

@router.get('/entitlements')
def entitlement_status(db:DB,who:Auth):
    if who.user.role!='DIRECTOR' and not {'inventory.view','vehicles.view','dismantling.manage'} & who.permissions:
        raise HTTPException(403,'Недостатньо прав для перегляду використання')
    result=entitlements.report(db,who.workspace_account_id)
    result.update(can_manage=who.user.role=='DIRECTOR' and who.actor_id==who.workspace_account_id,
        plans=entitlements.PLANS,packs={k:{'amount_minor':v[0],'capacity':v[1]} for k,v in entitlements.PACKS.items()},
        feature_enabled=entitlements.enabled())
    if not result['can_manage']:
        result.pop('plans');result.pop('packs')
        if 'team.view' not in who.permissions:result['usage']['employees']=None
    return result

@router.post('/bind')
def bind_workspace(db:DB,who:Auth):
    if global_finance.enabled():
        p=global_finance.bind(db,who);db.commit();return {'bound':True,'workspace_id':p.workspace_id,'mode':p.mode}
    p=entitlements.bind_owner(db,who);db.commit()
    return {'bound':True,'workspace_id':p.workspace_id,'mode':p.mode}

@router.post('/trial')
def start_trial(data:TrialInput,db:DB,who:Auth):
    if global_finance.enabled():
        p=global_finance.bind(db,who);db.commit()
        global_finance.request(who,'POST','/v1/trial',{'binding_id':p.global_binding_id,'plan':data.plan},binding=p)
        return global_finance.sync(db,who,p)
    entitlements.owner(who)
    p=entitlements.bind_owner(db,who);db.commit()
    from bot.billing.models import BillingError
    try:token=entitlements.local_bridge().trial(p.workspace_id,p.billing_account_id,data.plan)
    except BillingError as exc:raise HTTPException(409,str(exc)) from None
    entitlements.accept(db,token);db.commit()
    return entitlements.report(db,who.workspace_account_id)

@router.post('/sync')
def sync_entitlements(db:DB,who:Auth):
    if global_finance.enabled():return global_finance.sync(db,who)
    entitlements.owner(who);p=entitlements.bind_owner(db,who);db.commit()
    token=entitlements.local_bridge().latest(p.workspace_id,p.billing_account_id)
    if token:entitlements.accept(db,token);db.commit()
    return entitlements.report(db,who.workspace_account_id)

@router.post('/quote')
def addon_quote(data:QuoteInput,db:DB,who:Auth):
    entitlements.owner(who)
    from decimal import Decimal,ROUND_HALF_UP
    from datetime import datetime
    s=entitlements.state(db,who.workspace_account_id);p=entitlements.projection(db,who.workspace_account_id)
    if not p or not s['paid'] or s['status']=='GRACE':raise HTTPException(409,'Потрібний чинний період')
    stamp=entitlements.now()
    current=next(i for i in p.intervals if i['kind']!='addon' and datetime.fromisoformat(i['effective_from'])<=stamp<datetime.fromisoformat(i['effective_until']))
    a,b=(datetime.fromisoformat(current[k]) for k in ('effective_from','effective_until'))
    amount,capacity=entitlements.PACKS[data.pack]
    micros=lambda d:(d.days*86400+d.seconds)*1000000+d.microseconds
    due=int((Decimal(amount)*micros(b-stamp)/micros(b-a)).quantize(Decimal(1),rounding=ROUND_HALF_UP))
    return {'amount_minor':due,'full_amount_minor':amount,'currency':'UAH','capacity':capacity,
            'effective_until':b,'checkout_available':False,'cadence':'monthly'}

@router.post('/returns')
def verified_return(data:ReturnInput,db:DB,who:Auth):
    from app.models import Operation,Part,uid
    from app.models.entitlements import EntitlementReturn
    from app.permissions import require_permission
    from app.services.inventory import record,snapshot
    if not entitlements.enabled():raise HTTPException(503,'Новий контур вимкнено')
    require_permission(who,'inventory.adjust_quantity','sales.create')
    entitlements.lock(db,who.workspace_account_id)
    old=db.scalar(select(EntitlementReturn).where(EntitlementReturn.workspace_id==who.workspace_account_id,EntitlementReturn.request_key==data.request_key))
    if old:
        if (old.sale_id,old.quantity)!=(data.sale_id,data.quantity):raise HTTPException(409,'Конфлікт ключа повернення')
        return {'id':old.id,'replayed':True}
    sale=db.scalar(select(Operation).where(Operation.id==data.sale_id,Operation.account_id==who.workspace_account_id,Operation.type=='sale'))
    if not sale:raise HTTPException(404,'Підтверджений продаж не знайдено')
    sold=int(sale.before['quantity'])-int(sale.after['quantity'])
    returned=db.scalar(select(func.coalesce(func.sum(EntitlementReturn.quantity),0)).where(EntitlementReturn.sale_id==sale.id))
    if returned+data.quantity>sold:raise HTTPException(409,'Повернення перевищує продану кількість')
    part=db.scalar(select(Part).where(Part.id==sale.part_id,Part.account_id==who.workspace_account_id).with_for_update())
    if not part:raise HTTPException(409,'Історичний товар відсутній')
    before=snapshot(part);part.archived=False;part.quantity+=data.quantity;part.availability='present'
    row=EntitlementReturn(id=uid(),workspace_id=who.workspace_account_id,sale_id=sale.id,quantity=data.quantity,request_key=data.request_key)
    db.info['verified_entitlement_return']=True
    try:
        db.add(row);record(db,who.workspace_account_id,part,'return','Повернення за підтвердженим продажем',before,after_extra={'source_sale_id':sale.id})
        db.commit()
    finally:db.info.pop('verified_entitlement_return',None)
    return {'id':row.id,'replayed':False}


class GlobalPurchase(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sku:Literal['warehouse.standard','warehouse.premium','warehouse.slots.1','warehouse.slots.5','warehouse.slots.10']
    request_key:str=Field(min_length=1,max_length=160)
    quantity:int=Field(default=1,strict=True,ge=1,le=1000)

class GlobalProof(BaseModel):
    model_config=ConfigDict(extra='forbid')
    proof:str=Field(min_length=1,max_length=200000)

@router.get('/cabinet')
def global_cabinet(db:DB,who:Auth):
    if not global_finance.enabled():return {'enabled':False}
    can_manage=who.user.role=='DIRECTOR' and who.actor_id==who.workspace_account_id
    if not can_manage:return {'enabled':True,'can_manage':False}
    p=db.get(EntitlementWorkspace,who.workspace_account_id)
    if not p or not p.global_binding_id:return {'enabled':True,'can_manage':True,'bound':False,'environment':global_finance.environment()}
    p=global_finance.binding(db,who)
    result=global_finance.request(who,'GET','/v1/cabinet/'+p.global_binding_id,binding=p)
    result.update(enabled=True,bound=True,can_manage=True,entitlements=entitlements.report(db,who.workspace_account_id))
    return result

@router.post('/invoices')
def global_invoice(data:GlobalPurchase,db:DB,who:Auth):
    p=global_finance.binding(db,who)
    return global_finance.request(who,'POST','/v1/invoices',{'binding_id':p.global_binding_id,**data.model_dump()},binding=p)

def financial_id(value):
    from uuid import UUID
    try:UUID(value)
    except (ValueError,TypeError):raise HTTPException(422,'Некоректний фінансовий ідентифікатор') from None
    return value

@router.get('/invoices/{invoice}')
def global_invoice_view(invoice:str,db:DB,who:Auth):
    p=global_finance.binding(db,who)
    return global_finance.request(who,'GET','/v1/invoices/'+financial_id(invoice),binding=p)

@router.post('/invoices/{invoice}/void')
def global_invoice_void(invoice:str,db:DB,who:Auth):
    p=global_finance.binding(db,who)
    return global_finance.request(who,'POST','/v1/invoices/'+financial_id(invoice)+'/void',binding=p)

@router.get('/orders/{order}')
def global_order(order:str,db:DB,who:Auth):
    import re
    if not re.fullmatch(r'carpot-(sandbox|production)-[0-9a-f]{32}',order):raise HTTPException(422,'Некоректне замовлення')
    p=global_finance.binding(db,who)
    return global_finance.request(who,'GET','/v1/orders/'+order,binding=p)

@router.post('/orders/{order}/refresh')
def global_refresh(order:str,db:DB,who:Auth):
    import re
    if not re.fullmatch(r'carpot-(sandbox|production)-[0-9a-f]{32}',order):raise HTTPException(422,'Некоректне замовлення')
    p=global_finance.binding(db,who)
    return global_finance.request(who,'POST','/v1/orders/'+order+'/refresh',binding=p)

@router.post('/internal/entitlements')
def global_entitlement_delivery(data:GlobalProof,db:DB):
    return global_finance.apply(db,data.proof)
