from app.api.secure_route import SecureRoute
"""Workshop projections of the existing stock ledger. No second sales ledger."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import ConfigDict, Field
from sqlalchemy import select, func, or_, exists
from app.api.routes import DB, Auth
from app.models import Operation, Part, Account, Vehicle
from app.models.orders import OrderLine, Order, OrderEvent
from app.schemas import Input
from app.services.inventory import owned, snapshot, record

router = APIRouter(route_class=SecureRoute,prefix='/api/v1')

class NotesInput(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    # Compare-and-set protects against overwriting another editor's note.
    internal_notes: Annotated[str, Field(max_length=10000)]
    expected_notes: Annotated[str, Field(max_length=10000)]

class InspectionInput(Input):
    condition: Literal['used','new','damaged','refurbished'] | None = None
    availability: Literal['unchecked','present','absent','damaged'] | None = None

@router.patch('/parts/{id}/notes')
def notes(id: str, data: NotesInput, db: DB, who: Auth):
    row=owned(db,Part,id,who.workspace_account_id,lock=True,active=True)
    if row.internal_notes != data.expected_notes:
        raise HTTPException(409,'Нотатку вже змінено. Оновіть картку та порівняйте зміни.')
    before=snapshot(row);row.internal_notes=data.internal_notes
    if row.internal_notes!=before['internal_notes']:record(db,who.workspace_account_id,row,'part_update','Оновлено внутрішню нотатку',before)
    db.commit();return {**snapshot(row),'available_quantity':row.available_quantity}

@router.patch('/parts/{id}/inspection')
def inspection(id: str, data: InspectionInput, db: DB, who: Auth):
    row=owned(db,Part,id,who.workspace_account_id,lock=True,active=True);before=snapshot(row)
    if data.condition is not None:row.condition=data.condition
    if data.availability is not None:row.availability=data.availability
    if snapshot(row)!=before:record(db,who.workspace_account_id,row,'part_update','Оновлено стан / перевірку наявності',before)
    db.commit();return {**snapshot(row),'available_quantity':row.available_quantity}

@router.get('/workshop/readiness')
def readiness(db: DB, who: Auth):
    from app.api.orders import readiness as orders_readiness
    # Old inventory v5 and orders v6 stay unchanged; this is a separate capability.
    return {**orders_readiness(db,who),'contract_version':7,
        'features':['actual_quick_sale_price','ledger_sales_projection','notes_compare_and_set','inspection_patch']}

@router.get('/sales')
def sales(db: DB, who: Auth, q: str = Query('',max_length=200), vehicle_id: str | None = None,
          source: Literal['quick','order'] | None = None, date_from: datetime | None = None,
          date_to: datetime | None = None, offset: int = Query(0,ge=0), limit: int = Query(50,ge=1,le=100)):
    if date_from and date_from.tzinfo is None:date_from=date_from.replace(tzinfo=timezone.utc)
    if date_to and date_to.tzinfo is None:date_to=date_to.replace(tzinfo=timezone.utc)
    scope=select(Operation).where(Operation.account_id==who.workspace_account_id,Operation.type=='sale')
    order_sale=exists(select(OrderLine.id).where(OrderLine.account_id==who.workspace_account_id,OrderLine.sale_operation_id==Operation.id))
    if source:scope=scope.where(order_sale if source=='order' else ~order_sale)
    if vehicle_id:scope=scope.where(Operation.vehicle_id==vehicle_id)
    if date_from and date_to and date_from>date_to:raise HTTPException(422,'Некоректний період')
    if date_from:scope=scope.where(Operation.created_at>=date_from)
    if date_to:scope=scope.where(Operation.created_at<=date_to)
    if q.strip():scope=scope.where(or_(*[func.lower(Operation.after[k].as_string()).contains(q.strip().lower(),autoescape=True) for k in ('name','oem_number','article_number')]))
    total=db.scalar(select(func.count()).select_from(scope.subquery()))
    ops=list(db.scalars(scope.order_by(Operation.created_at.desc(),Operation.id).offset(offset).limit(limit)))
    ids=[op.id for op in ops]
    linked={line.sale_operation_id:(line,order) for line,order in db.execute(select(OrderLine,Order).join(Order,Order.id==OrderLine.order_id).where(OrderLine.account_id==who.workspace_account_id,Order.account_id==who.workspace_account_id,OrderLine.sale_operation_id.in_(ids)))} if ids else {}
    events={}
    if linked:
        for e in db.scalars(select(OrderEvent).where(OrderEvent.account_id==who.workspace_account_id,OrderEvent.order_id.in_([o.id for _,o in linked.values()]),OrderEvent.type=='sale_confirmed')):
            events[e.order_id]=e.data
    actor_ids={op.actor_id for op in ops}
    actors={a.id:a.name for a in db.scalars(select(Account).where(Account.id.in_(actor_ids),or_(Account.id==who.workspace_account_id,Account.workspace_account_id==who.workspace_account_id)))}
    donor_ids={op.vehicle_id for op in ops if op.vehicle_id}
    donors={v.id:snapshot(v) for v in db.scalars(select(Vehicle).where(Vehicle.id.in_(donor_ids),Vehicle.account_id==who.workspace_account_id))}
    items=[]
    for op in ops:
        financial=op.after.get('sale') or {};link=linked.get(op.id)
        # Historical order prices are recorded independently of current Part prices.
        if not financial and link:
            line,order=link;event=events.get(order.id,{})
            sold=next((x for x in event.get('lines',[]) if x.get('sale_operation_id')==op.id),None)
            if sold:
                financial={'unit_price':sold['unit_price'],'currency':sold['currency'],
                    'total':sold['line_total'],'donor':sold.get('donor_snapshot'),
                    'buyer_name':event.get('contact_name'),'buyer_phone':event.get('contact_phone')}
        quantity=op.before.get('quantity',0)-op.after.get('quantity',0)
        items.append({'id':op.id,'part_id':op.part_id,'name':op.after.get('name'),'vehicle_id':op.vehicle_id,
            'donor':financial.get('donor') or donors.get(op.vehicle_id),'donor_is_current':not bool(financial.get('donor')),
            'quantity':quantity,'unit_price':financial.get('unit_price'),'currency':financial.get('currency'),
            'total':financial.get('total'),'price_recorded':financial.get('unit_price') is not None,
            'source':'order' if link else 'quick','order_id':link[1].id if link else None,
            'buyer_name':financial.get('buyer_name'),'actor_name':financial.get('actor_name') or actors.get(op.actor_id),
            'note':op.reason,'created_at':op.created_at.isoformat()})
    return {'items':items,'total':total,'offset':offset,'limit':limit}
