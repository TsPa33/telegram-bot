"""Read-only, bounded UNION journal. Orders are commitments, sale rows are proceeds."""
from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,HTTPException,Query
from sqlalchemy import select,func,literal,or_,and_,exists,union_all,cast,String,false,case
from app.api.secure_route import SecureRoute
from app.api.routes import DB,Auth
from app.api.orders import phone_query
from app.models import Account,Order,OrderLine,OrderEvent,Operation,Part
from app.services import orders
from app.services.sales_projection import project_sales
router=APIRouter(route_class=SecureRoute,prefix='/api/v1/sales-center',tags=['Sales Center'])

def creator(order_id,workspace):
    return select(OrderEvent.actor_id).where(OrderEvent.account_id==workspace,OrderEvent.order_id==order_id,OrderEvent.type=='created').order_by(OrderEvent.created_at,OrderEvent.id).limit(1).scalar_subquery()

def phone_match(column,digits):
    raw=func.regexp_replace(func.coalesce(column,''),'[^0-9]','','g')
    normalized=case((and_(func.length(raw)==10,raw.startswith('0')),literal('38')+raw),(raw.startswith('00'),func.substr(raw,3)),else_=raw)
    return normalized.contains(digits,autoescape=True)

@router.get('/managers')
def managers(db:DB,who:Auth):
    if not ({'sales.view','orders.view'} & who.permissions):raise HTTPException(403,'Недостатньо прав')
    # Actual workspace identities, including inactive actors; no email/phone/role leakage.
    people=db.scalars(select(Account).where(or_(Account.id==who.workspace_account_id,Account.workspace_account_id==who.workspace_account_id)).order_by(Account.name,Account.id).limit(1001)).all()
    if len(people)>1000:raise HTTPException(422,'Забагато працівників для списку фільтра')
    return {'items':[{'id':p.id,'name':p.name,'active':p.is_active} for p in people]}

@router.get('')
def journal(db:DB,who:Auth,kind:Literal['all','orders','sales']='all',q:str=Query('',max_length=200),phone:str=Query('',max_length=50),manager_id:str|None=Query(None,max_length=36),
            number:int|None=Query(None,gt=0),status:Literal['new','reserved','shipped','completed','cancelled','sold']|None=None,vehicle_id:str|None=Query(None,max_length=36),
            date_from:datetime|None=None,date_to:datetime|None=None,offset:int=Query(0,ge=0,le=100000),limit:int=Query(50,ge=1,le=100)):
    can_sales='sales.view' in who.permissions;can_orders='orders.view' in who.permissions
    if not(can_sales or can_orders):raise HTTPException(403,'Недостатньо прав')
    if phone and not can_orders:raise HTTPException(403,'Для пошуку за телефоном потрібен перегляд замовлень')
    digits=phone_query(phone) if phone else None
    if date_from and date_from.tzinfo is None:date_from=date_from.replace(tzinfo=timezone.utc)
    if date_to and date_to.tzinfo is None:date_to=date_to.replace(tzinfo=timezone.utc)
    if date_from and date_to and date_from>date_to:raise HTTPException(422,'Некоректний період')
    workspace=who.workspace_account_id
    of=[Order.account_id==workspace];sf=[Operation.account_id==workspace,Operation.type=='sale']
    if not can_orders or kind=='sales':of.append(false())
    if not can_sales or kind=='orders':sf.append(false())
    linked=select(OrderLine.order_id).where(OrderLine.account_id==workspace,OrderLine.sale_operation_id==Operation.id).correlate(Operation)
    if number is not None:
        of.append(Order.number==number);sf.append(exists(select(Order.id).where(Order.account_id==workspace,Order.number==number,Order.id.in_(linked))))
    if status:
        of.append(Order.sold_at.is_not(None) if status=='sold' else Order.status==status)
        if status!='sold':sf.append(false())
    if manager_id:of.append(creator(Order.id,workspace)==manager_id);sf.append(Operation.actor_id==manager_id)
    if vehicle_id:
        of.append(exists(select(OrderLine.id).where(OrderLine.account_id==workspace,OrderLine.order_id==Order.id,OrderLine.active,or_(OrderLine.donor_snapshot['id'].as_string()==vehicle_id,and_(OrderLine.donor_snapshot['id'].as_string().is_(None),exists(select(Part.id).where(Part.id==OrderLine.part_id,Part.account_id==workspace,Part.vehicle_id==vehicle_id)))))))
        sf.append(Operation.vehicle_id==vehicle_id)
    if digits:
        of.append(phone_match(Order.contact_phone_normalized,digits))
        modern=phone_match(Operation.after['sale']['buyer_phone'].as_string(),digits)
        legacy=exists(select(OrderEvent.id).where(OrderEvent.account_id==workspace,OrderEvent.order_id.in_(linked),OrderEvent.type=='sale_confirmed',phone_match(OrderEvent.data['contact_phone'].as_string(),digits)))
        sf.append(or_(modern,legacy))
    if q.strip():
        text=q.strip().lower();of.append(or_(func.lower(Order.contact_name).contains(text,autoescape=True),exists(select(OrderLine.id).where(OrderLine.order_id==Order.id,OrderLine.account_id==workspace,OrderLine.active,func.lower(OrderLine.name).contains(text,autoescape=True)))))
        sf.append(or_(*[func.lower(Operation.after[k].as_string()).contains(text,autoescape=True) for k in ('name','oem_number','article_number')]))
    for column,value,op in [('created_at',date_from,'from'),('created_at',date_to,'to')]:
        if value:
            of.append(Order.created_at>=value if op=='from' else Order.created_at<=value)
            sf.append(Operation.created_at>=value if op=='from' else Operation.created_at<=value)
    scope=union_all(select(Order.id.label('id'),Order.created_at.label('created_at'),literal('order').label('kind')).where(*of),select(Operation.id.label('id'),Operation.created_at.label('created_at'),literal('sale').label('kind')).where(*sf)).subquery()
    total=db.scalar(select(func.count()).select_from(scope));page=list(db.execute(select(scope).order_by(scope.c.created_at.desc(),scope.c.kind,scope.c.id).offset(offset).limit(limit)).mappings())
    sale_ids=[r['id'] for r in page if r['kind']=='sale'];sale_rows=list(db.scalars(select(Operation).where(Operation.account_id==workspace,Operation.id.in_(sale_ids)))) if sale_ids else []
    sales={s['id']:s for s in project_sales(db,who,sale_rows,center=True)};result=[]
    order_ids=[r['id'] for r in page if r['kind']=='order'];order_rows={r.id:r for r in db.scalars(select(Order).where(Order.account_id==workspace,Order.id.in_(order_ids)))} if order_ids else {}
    events=list(db.scalars(select(OrderEvent).where(OrderEvent.account_id==workspace,OrderEvent.order_id.in_(order_ids),OrderEvent.type=='created').order_by(OrderEvent.created_at,OrderEvent.id))) if order_ids else []
    created={}
    for e in events:created.setdefault(e.order_id,e)
    actors={p.id:p.name for p in db.scalars(select(Account).where(or_(Account.id==workspace,Account.workspace_account_id==workspace),Account.id.in_({e.actor_id for e in events})))} if events else {}
    amounts={};positions={}
    if order_ids:
        for oid,currency,count,amount in db.execute(select(OrderLine.order_id,OrderLine.currency,func.count(),func.sum(OrderLine.line_total)).where(OrderLine.account_id==workspace,OrderLine.order_id.in_(order_ids),OrderLine.active).group_by(OrderLine.order_id,OrderLine.currency)):
            amounts.setdefault(oid,{})[currency]=format(amount,'.2f');positions[oid]=positions.get(oid,0)+count
    for r in page:
        if r['kind']=='sale':
            s=sales[r['id']];result.append({**s,'kind':'sale','number':s.get('order_number'),'contact_name':s.get('buyer_name'),'contact_phone':s.get('buyer_phone'),'manager_id':s['actor_id'],'manager_name':s['actor_name'],'position_count':1,'status':'sold','totals_by_currency':{s['currency']:s['total']} if s['price_recorded'] and s.get('total') is not None and s.get('currency') else {}})
        else:
            order=order_rows[r['id']];event=created.get(order.id);identity=(event.data.get('actor_identity') or {}) if event else {}
            result.append({**orders.snapshot(order),'totals_by_currency':amounts.get(order.id,{}),'kind':'order','manager_id':event.actor_id if event else None,'manager_name':(identity.get('name') or actors.get(event.actor_id)) if event else None,'position_count':positions.get(order.id,0),'source':'order','order_id':order.id,'name':None})
    status_counts=[{'status':status,'count':count,'sold_count':sold} for status,count,sold in db.execute(select(Order.status,func.count(),func.count().filter(Order.sold_at.is_not(None))).where(*of).group_by(Order.status))]
    return {'order_status_counts':status_counts,'items':result,'total':total,'offset':offset,'limit':limit,'money_scope':'order_commitments_and_sale_proceeds_are_distinct'}
