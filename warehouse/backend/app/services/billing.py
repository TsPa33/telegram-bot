"""Workspace billing, disabled until sandbox provider contract is verified.

No external network calls. Credit/catalogue commit shares the caller transaction.
"""
import os,base64,hashlib,hmac,json,calendar
from datetime import timedelta
from decimal import Decimal,InvalidOperation
from sqlalchemy import select,func,or_
from fastapi import HTTPException
from app.config import is_staging
from app.models import Account,Vehicle,now,WorkspaceSubscription,BillingPayment,DismantlingCredit,DismantlingUsage,BillingEvent

PLANS={'standard':{'name':'Standard','amount':1000,'employees':5,'credits':10},'premium':{'name':'Premium','amount':4500,'employees':10,'credits':50}}
PACKS={'pack_1':(300,1),'pack_5':(1200,5),'pack_10':(2000,10)}

def fixture_contract_enabled():
    from app.config import database_url
    from sqlalchemy.engine import make_url
    if not is_staging() or os.getenv('WAREHOUSE_BILLING_FIXTURE_CONTRACT')!='true':return False
    url=make_url(database_url())
    return url.host in ('127.0.0.1','localhost') and url.database.endswith('_test')

def enabled():
    # Provider integration is unverified: enforcement stays local-test-only.
    return os.getenv('WAREHOUSE_BILLING_ENABLED','false').lower()=='true' and fixture_contract_enabled()

def next_month(start):
    month=start.month%12+1;year=start.year+(start.month==12)
    return start.replace(year=year,month=month,day=min(start.day,calendar.monthrange(year,month)[1]))

def mark_renewal_failed(db,workspace,provider_id):
    lock(db,workspace);s=subscription(db,workspace)
    if not s or not s.auto_renew or not provider_id or s.provider_id!=provider_id:raise HTTPException(409,'Підписку провайдера не підтверджено')
    days=int(os.getenv('WAREHOUSE_BILLING_GRACE_DAYS','3'))
    if not 0<=days<=30:raise RuntimeError('WAREHOUSE_BILLING_GRACE_DAYS must be 0..30')
    s.status='past_due';s.grace_end=s.period_end+timedelta(days=days)

def exempt(workspace):return is_staging() and workspace in {x.strip() for x in os.getenv('WAREHOUSE_BILLING_DEMO_WORKSPACES','').split(',') if x.strip()}
def lock(db,workspace):
    owner=db.scalar(select(Account).where(Account.id==workspace).with_for_update().execution_options(populate_existing=True))
    if not owner or owner.role!='DIRECTOR' or owner.workspace_account_id is not None:raise HTTPException(404,'Робочий простір не знайдено')
    return owner

def subscription(db,workspace):return db.get(WorkspaceSubscription,workspace,populate_existing=True)
def active(s):return bool(s and s.status in ('active','past_due') and s.period_end and (s.period_end>now() or s.status=='past_due' and s.grace_end and s.grace_end>now()))
def require_active(db,workspace):
    if enabled() and not exempt(workspace) and not active(subscription(db,workspace)):raise HTTPException(402,'Підписка завершена. Доступний перегляд і поновлення оплати.')

def employee_limit(db,workspace,target_id=None):
    if not enabled() or exempt(workspace):return
    lock(db,workspace);require_active(db,workspace);s=subscription(db,workspace)
    count=db.scalar(select(func.count()).select_from(Account).where(Account.workspace_account_id==workspace,Account.id!=workspace,Account.is_active.is_(True),Account.id!=target_id if target_id else True))
    if count>=PLANS[s.plan]['employees']:raise HTTPException(409,'Досягнуто ліміт активних працівників тарифу')

def balance(db,workspace):
    grants=list(db.scalars(select(DismantlingCredit).where(DismantlingCredit.workspace_id==workspace,or_(DismantlingCredit.expires_at.is_(None),DismantlingCredit.expires_at>now()))))
    reserved=dict(db.execute(select(DismantlingUsage.credit_id,func.count()).where(DismantlingUsage.workspace_id==workspace,DismantlingUsage.status=='reserved').group_by(DismantlingUsage.credit_id)).all())
    return {kind:sum(max(0,g.granted-g.used-reserved.get(g.id,0)) for g in grants if g.source==kind) for kind in ('monthly','extra')}

def reserve(db,workspace,vehicle,ktype):
    if not enabled() or exempt(workspace):return None
    lock(db,workspace);require_active(db,workspace)
    donor=db.scalar(select(Vehicle).where(Vehicle.id==vehicle,Vehicle.account_id==workspace))
    if not donor:raise HTTPException(404,'Автомобіль не знайдено')
    if not ktype or donor.ktype!=ktype:raise HTTPException(409,'Модифікація не відповідає автомобілю')
    existing=db.scalar(select(DismantlingUsage).where(DismantlingUsage.workspace_id==workspace,DismantlingUsage.vehicle_id==vehicle,DismantlingUsage.ktype==ktype))
    if existing and existing.status=='done':return None
    if existing and existing.status=='reserved':raise HTTPException(409,'Отримання каталогу вже виконується. Скористайтеся відновленням збереженої відповіді.')
    grants=list(db.scalars(select(DismantlingCredit).where(DismantlingCredit.workspace_id==workspace,or_(DismantlingCredit.expires_at.is_(None),DismantlingCredit.expires_at>now())).order_by(DismantlingCredit.source.desc(),DismantlingCredit.created_at)))
    # Explicit monthly-first ordering; purchased packs never expire at renewal.
    grants.sort(key=lambda g:(g.source!='monthly',g.created_at))
    credit=None
    for g in grants:
        pending=db.scalar(select(func.count()).select_from(DismantlingUsage).where(DismantlingUsage.credit_id==g.id,DismantlingUsage.status=='reserved'))
        if g.granted-g.used-pending>0:credit=g;break
    if not credit:raise HTTPException(402,'Немає доступних розборів. Поповніть баланс.')
    row=existing or DismantlingUsage(workspace_id=workspace,vehicle_id=vehicle,ktype=ktype,operation_key=f'catalogue:{vehicle}:{ktype}')
    row.status='reserved';row.credit_id=credit.id;row.updated_at=now();db.add(row);db.commit();return row.id

def finalize(db,workspace,usage_id,*,complete):
    if not usage_id:return
    lock(db,workspace)
    row=db.scalar(select(DismantlingUsage).where(DismantlingUsage.id==usage_id,DismantlingUsage.workspace_id==workspace).with_for_update())
    if not row or row.status!='reserved':return
    if complete:
        credit=db.get(DismantlingCredit,row.credit_id,with_for_update=True);credit.used+=1;row.status='done'
    else:row.status='failed'
    row.updated_at=now()

def signature(data,key):return base64.b64encode(hashlib.sha1((key+data+key).encode()).digest()).decode()
def decode(data,sig,key):
    if not isinstance(data,str) or not isinstance(sig,str) or not isinstance(key,str) or not key or len(data)>64000 or not hmac.compare_digest(signature(data,key),sig):raise HTTPException(400,'Недійсний підпис платежу')
    try:
        payload=json.loads(base64.b64decode(data,validate=True))
        if not isinstance(payload,dict):raise ValueError()
        return payload
    except (ValueError,TypeError):raise HTTPException(400,'Некоректне повідомлення платежу') from None

def process_event(db,payload,event_id):
    """Mock-contract ledger processor. Public webhook remains disabled pending docs."""
    if not fixture_contract_enabled():
        raise HTTPException(503,'Mock-контракт доступний лише в окремій локальній тестовій БД')
    order=str(payload.get('order_id',''));p=db.get(BillingPayment,order)
    if not p:raise HTTPException(404,'Платіж не знайдено')
    lock(db,p.workspace_id);db.refresh(p,with_for_update=True)
    previous=db.get(BillingEvent,event_id)
    if previous:
        if previous.payment_id!=p.id or previous.workspace_id!=p.workspace_id:raise HTTPException(409,'Конфлікт ідентифікатора події')
        return 'duplicate'
    try:amount=Decimal(str(payload.get('amount')))
    except InvalidOperation:raise HTTPException(400,'Некоректна сума') from None
    if not amount.is_finite() or amount!=p.amount or payload.get('currency')!='UAH' or p.currency!='UAH':raise HTTPException(400,'Сума або валюта не відповідає замовленню')
    if payload.get('sandbox') not in (1,'1') or payload.get('status') not in ('sandbox','failure','error'):raise HTTPException(400,'Дозволені лише sandbox-події перевіреного локального контракту')
    good=payload['status']=='sandbox';db.add(BillingEvent(id=event_id,workspace_id=p.workspace_id,payment_id=p.id,kind=payload['status'],status='accepted'))
    if p.status=='confirmed':db.commit();return 'already_confirmed'
    if not good:
        p.status='failed'
        # A failed new checkout never downgrades a previously paid subscription.
        db.commit();return 'failed'
    if p.product in PLANS:
        plan=PLANS[p.product]
        if p.amount!=plan['amount']:raise HTTPException(400,'Продукт не відповідає сумі')
        s=subscription(db,p.workspace_id)
        if s and active(s):raise HTTPException(409,'Зміна активної підписки потребує підтвердженого контракту провайдера')
        start=now();end=next_month(start)
        # Local fixture calendar only, not a claim about provider recurrence.
        s=s or WorkspaceSubscription(workspace_id=p.workspace_id)
        s.plan=p.product;s.status='active';s.period_start=start;s.period_end=end;s.grace_end=None;s.auto_renew=False;db.add(s)
        source='monthly';quantity=plan['credits'];expiry=end
    elif p.product in PACKS:
        expected,quantity=PACKS[p.product]
        if p.amount!=expected:raise HTTPException(400,'Продукт не відповідає сумі')
        source='extra';expiry=None
    else:raise HTTPException(400,'Невідомий продукт')
    p.status='confirmed';p.confirmed_at=now();p.provider_id=str(payload.get('payment_id',''))[:160] or None
    db.add(DismantlingCredit(workspace_id=p.workspace_id,payment_id=p.id,source=source,granted=quantity,used=0,expires_at=expiry));db.commit();return 'confirmed'
