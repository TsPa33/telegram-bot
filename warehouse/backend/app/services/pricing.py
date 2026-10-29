"""Reviewed seller prices; Part/Operation remain authoritative. Never stock()."""
from datetime import timedelta
from decimal import Decimal,ROUND_HALF_UP
from sqlalchemy import select
from fastapi import HTTPException
from app.models import Part,Operation,PriceDecision,StockRequest
from app.services.inventory import record,snapshot
from app.services.price_guidance import guidance,parts_for,utcnow,VERSION
from app.services.catalogue_format import digest

def reauthorize(db,who):
    # Recheck after waiting for workspace/Part locks, including cached replays.
    from app.models import Account,Session,now
    from app.permissions import effective
    user=db.scalar(select(Account).where(Account.id==who.actor_id).execution_options(populate_existing=True))
    session=db.scalar(select(Session).where(Session.token_hash==who.session.token_hash).execution_options(populate_existing=True))
    if not user or not user.is_active or not session or session.expires_at<=now():raise HTTPException(401,'Сесію відкликано або доступ заблоковано')
    if (user.workspace_account_id or user.id)!=who.workspace_account_id or user.must_change_password:raise HTTPException(403,'Доступ змінено; увійдіть повторно')
    if 'parts.change_price' not in effective(user):raise HTTPException(403,'Немає дозволу змінювати ціни')
    who.user=user

def revisions(db,parts):
    from sqlalchemy import func
    latest={pid:[oid,count] for pid,oid,count in db.execute(select(Operation.part_id,Operation.id,func.count(Operation.id).over(partition_by=Operation.part_id)).where(Operation.part_id.in_([p.id for p in parts])).distinct(Operation.part_id).order_by(Operation.part_id,Operation.created_at.desc(),Operation.id.desc()))}
    return {p.id:digest([p.id,p.account_id,str(p.selling_price) if p.selling_price is not None else None,p.currency,p.archived,p.assortment_enabled,p.quantity,p.reserved_quantity,p.condition,p.oem_number,p.vehicle_id,p.canonical_placement_id,p.compatibility_notes,p.description,latest.get(p.id)]) for p in parts}

def set_price(db,part,value,currency,account,*,decision=None):
    before=snapshot(part);part.selling_price=value;part.currency=currency
    if snapshot(part)!=before:record(db,account,part,'part_update','Масове встановлення перевіреної ціни' if decision else 'Оновлено ціну та валюту',before,after_extra={'pricing_decision_id':decision} if decision else None)

def manual(db,part,who,data):
    reauthorize(db,who)
    fp=digest(['seller_price',part.id,data.model_dump(mode='json',exclude={'request_key'})])
    if data.request_key:
        old=db.scalar(select(StockRequest).where(StockRequest.account_id==who.workspace_account_id,StockRequest.request_key==str(data.request_key)))
        if old:
            if old.actor_id!=who.actor_id or old.fingerprint!=fp:raise HTTPException(409,'Ключ уже використано для іншого запиту')
            return old.response
    if part.archived:raise HTTPException(404,'Запис не знайдено')
    if data.expected_token and revisions(db,[part])[part.id]!=data.expected_token:raise HTTPException(409,'Ціну або деталь змінено. Оновіть картку перед редагуванням')
    set_price(db,part,data.selling_price,data.currency,who.workspace_account_id);db.flush()
    result={**snapshot(part),'available_quantity':part.available_quantity}
    if data.request_key or data.expected_token:result['price_token']=revisions(db,[part])[part.id]
    if data.request_key:db.add(StockRequest(account_id=who.workspace_account_id,actor_id=who.actor_id,part_id=part.id,request_key=str(data.request_key),fingerprint=fp,response=result))
    return result

def comparable(row,currency):
    cohorts=[c for c in row['cohorts'] if c['level']=='A' and c['currency']==currency]
    return cohorts[0] if len(cohorts)==1 else None

def calculate(db,parts,account,command):
    market=guidance(db,parts,account) if command['mode']!='fixed' else {p.id:{'label':'Власна фіксована ціна','cohorts':[]} for p in parts}
    versions=revisions(db,parts);rows=[]
    for p in parts:
        g=market[p.id];c=comparable(g,command['currency']);reason=None;value=None
        if p.archived or not p.assortment_enabled or p.quantity<=0:reason='Неактивна, архівна або нульовий залишок'
        elif p.currency!=command['currency']:reason='Валюта Part не збігається; конвертація заборонена'
        elif p.selling_price is not None and not command['overwrite']:reason='Власну ціну збережено; потрібен явний дозвіл перезапису'
        elif command['mode']!='fixed' and not c:reason='Немає єдиної точної когорти з 3+ пропозиціями у цій валюті'
        else:
            value=Decimal(command['fixed_price']) if command['mode']=='fixed' else Decimal(c['median'])
            if command['mode']=='discount':value*=1-Decimal(command['percent'])/100
            if command['mode']=='markup':value*=1+Decimal(command['percent'])/100
            step=Decimal(command['rounding']);value=(value/step).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*step
            value=value.quantize(Decimal('.01'))
            if value>Decimal('999999999999.99'):reason='Ціна перевищує допустиму межу';value=None
        if value is not None and value==p.selling_price and not reason:reason='Ціна вже відповідає розрахунку'
        rows.append(dict(part_id=p.id,name=p.name,current_price=str(p.selling_price) if p.selling_price is not None else None,new_price=str(value) if value is not None else None,currency=p.currency,reason=reason,
            source='Явно задана ціна власника' if command['mode']=='fixed' else 'Перевірена медіана' if c else g['label'],cohort=c,part_revision=versions[p.id]))
    fingerprint=digest([VERSION,command,versions,market])
    return dict(items=rows,changed=sum(not r['reason'] for r in rows),skipped=sum(bool(r['reason']) for r in rows),policy=VERSION,rule={k:v for k,v in command.items() if k!='ids'}),fingerprint

def owner(who):
    if who.user.role!='DIRECTOR' or who.actor_id!=who.workspace_account_id:raise HTTPException(403,'Масові ціни доступні лише власнику цього workspace')

def preview(db,who,data):
    reauthorize(db,who);owner(who);cmd=data.model_dump(mode='json',exclude={'request_key'})
    previous=db.scalar(select(PriceDecision).where(PriceDecision.account_id==who.workspace_account_id,PriceDecision.request_key==str(data.request_key)))
    if previous:
        if previous.actor_id!=who.actor_id or previous.command!=cmd:raise HTTPException(409,'Ключ перевірки вже використано')
        return view(previous)
    parts=parts_for(db,who.workspace_account_id,data.ids,lock=True)
    report,fp=calculate(db,parts,who.workspace_account_id,cmd)
    now=utcnow();job=PriceDecision(account_id=who.workspace_account_id,actor_id=who.actor_id,request_key=str(data.request_key),fingerprint=fp,token=digest([fp,str(data.request_key),who.actor_id]),command=cmd,report=report,expires_at=now+timedelta(minutes=15))
    db.add(job);db.flush();return view(job)

def view(job):return dict(id=job.id,status=job.status,token=job.token,command=job.command,report=job.report,expires_at=job.expires_at.isoformat())

def apply(db,who,id,data):
    reauthorize(db,who);owner(who)
    job=db.scalar(select(PriceDecision).where(PriceDecision.id==id,PriceDecision.account_id==who.workspace_account_id).with_for_update())
    if not job or job.actor_id!=who.actor_id:raise HTTPException(404,'Перевірку власника не знайдено')
    if data.token!=job.token:raise HTTPException(409,'Підтвердження не відповідає перевірці')
    if job.status=='applied':
        if job.apply_key!=str(data.request_key):raise HTTPException(409,'Цю перевірку вже застосовано іншим запитом')
        return view(job)
    other=db.scalar(select(PriceDecision.id).where(PriceDecision.account_id==who.workspace_account_id,PriceDecision.apply_key==str(data.request_key)))
    if other:raise HTTPException(409,'Ключ застосування вже використано')
    if utcnow()>job.expires_at:raise HTTPException(409,'Перевірка цін застаріла; побудуйте нову')
    from sqlalchemy import text
    from app.services.catalogue_import import LOCK
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK}):raise HTTPException(409,'Каталог оновлюється; повторіть після завершення')
    parts=parts_for(db,who.workspace_account_id,job.command['ids'],lock=True)
    report,fp=calculate(db,parts,who.workspace_account_id,job.command)
    if fp!=job.fingerprint:raise HTTPException(409,'Деталі або ринкові ціни змінилися; потрібен новий preview')
    mapping={p.id:p for p in parts}
    for row in report['items']:
        if not row['reason']:set_price(db,mapping[row['part_id']],Decimal(row['new_price']),row['currency'],who.workspace_account_id,decision=job.id)
    job.status='applied';job.apply_key=str(data.request_key);job.report={**report,'committed':True}
    db.flush();return view(job)

def valuation(db,parts,account):
    parts=[p for p in parts if not p.archived and p.assortment_enabled and p.quantity>0];market=guidance(db,parts,account);groups={}
    for p in parts:
        b=groups.setdefault(p.currency,dict(currency=p.currency,positions=0,units=0,reserved_units=0,own_total=Decimal(0),own_reserved=Decimal(0),market_total=Decimal(0),market_reserved=Decimal(0),own_priced=0,market_priced=0))
        b['positions']+=1;b['units']+=p.quantity;b['reserved_units']+=p.reserved_quantity
        if p.selling_price is not None:b['own_total']+=p.quantity*p.selling_price;b['own_reserved']+=p.reserved_quantity*p.selling_price;b['own_priced']+=1
        c=comparable(market[p.id],p.currency)
        if c:
            b['market_total']+=p.quantity*Decimal(c['median']);b['market_reserved']+=p.reserved_quantity*Decimal(c['median']);b['market_priced']+=1
    for b in groups.values():
        b['own_available']=b['own_total']-b['own_reserved'];b['market_available']=b['market_total']-b['market_reserved']
        for kind in ('own','market'):
            b[kind+'_unpriced']=b['positions']-b[kind+'_priced'];b[kind+'_coverage_percent']=round(100*b[kind+'_priced']/b['positions'],2)
            for suffix in ('total','reserved','available'):b[kind+'_'+suffix]=str(b[kind+'_'+suffix]) if b[kind+'_priced'] else None
    return dict(by_currency=list(groups.values()),positions=len(parts),policy=VERSION,label='Інформаційна оцінка непроданого залишку; резерв включений один раз, не виручка чи прибуток')
