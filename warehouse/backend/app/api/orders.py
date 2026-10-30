from app.api.secure_route import SecureRoute
"""Additive authenticated orders API; the v5 inventory contract stays available."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from app.api.routes import DB, Auth
from app.models import Account,Buyer, Order, OrderEvent, OrderLine, OrderRequest, OrderReservation,Part
from app.schemas.orders import BuyerInput, CreateOrder, UpdateOrder, LinesInput, OrderAction, OrderStatus, normalize_phone
from app.services import orders as service
from app.services.inventory import owned, snapshot

router=APIRouter(route_class=SecureRoute,prefix='/api/v1',tags=['Buyers and orders'])


def phone_query(value):
    try:return normalize_phone(value,partial=True)
    except ValueError:raise HTTPException(422,'Для пошуку телефону вкажіть щонайменше 3 цифри та стандартні розділювачі') from None


@router.post('/buyers',status_code=201)
def buyer_create(data:BuyerInput,db:DB,who:Auth):return service.save_buyer(db,who.workspace_account_id,data)


@router.get('/buyers')
def buyers(db:DB,who:Auth,phone:str=Query('',max_length=50),offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
    stmt=select(Buyer).where(Buyer.account_id==who.workspace_account_id)
    if phone:
        digits=phone_query(phone);stmt=stmt.where(or_(Buyer.phone_normalized.contains(digits),Buyer.additional_phone_normalized.contains(digits)))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'items':[snapshot(row) for row in db.scalars(stmt.order_by(Buyer.created_at.desc(),Buyer.id).offset(offset).limit(limit))],'total':total,'offset':offset,'limit':limit}


@router.get('/buyers/{id}')
def buyer_get(id:str,db:DB,who:Auth):return snapshot(owned(db,Buyer,id,who.workspace_account_id))


@router.put('/buyers/{id}')
def buyer_update(id:str,data:BuyerInput,db:DB,who:Auth):return service.save_buyer(db,who.workspace_account_id,data,id)


@router.get('/orders/readiness')
def readiness(db:DB,who:Auth):
    from app.staging import migration_heads
    try:
        versions=frozenset(db.execute(text('SELECT version_num FROM alembic_version')).scalars())
        if versions!=migration_heads():raise HTTPException(503,'Orders migrations are not ready')
        for model in (Buyer,Order,OrderLine,OrderReservation,OrderEvent,OrderRequest):db.execute(select(model).limit(0))
    except SQLAlchemyError:raise HTTPException(503,'Orders schema is not ready') from None
    return {'status':'ready','contract_version':6,'required_revision':'d86f21a90b34','database_revisions':sorted(versions),
            'features':['buyers','orders','assigned_reservations','explicit_order_sale','order_request_replay']}


@router.post('/orders',status_code=201)
def create_order(data:CreateOrder,db:DB,who:Auth):
    return service.command(db,who.workspace_account_id,'orders:create',data,lambda:service.create(db,who.workspace_account_id,data))


@router.get('/orders')
def order_list(db:DB,who:Auth,q:str=Query('',max_length=100),phone:str=Query('',max_length=50),number:int|None=Query(None,gt=0),
               status:Literal['new','reserved','shipped','completed','cancelled']|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
    stmt=select(Order).where(Order.account_id==who.workspace_account_id)
    if status:stmt=stmt.where(Order.status==status)
    if number is not None:stmt=stmt.where(Order.number==number)
    def matching_phone(digits):
        buyer_ids=select(Buyer.id).where(Buyer.account_id==who.workspace_account_id,or_(Buyer.phone_normalized.contains(digits),Buyer.additional_phone_normalized.contains(digits)))
        return or_(Order.contact_phone_normalized.contains(digits),Order.buyer_id.in_(buyer_ids))
    if phone:stmt=stmt.where(matching_phone(phone_query(phone)))
    if q:
        search=q.strip().lstrip('№#').strip();conditions=[]
        if search.isascii() and search.isdigit():conditions.append(cast(Order.number,String).startswith(search))
        try:conditions.append(matching_phone(normalize_phone(search,partial=True)))
        except ValueError:pass
        stmt=stmt.where(or_(*conditions) if conditions else text('false'))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'items':[service.view(db,row) for row in db.scalars(stmt.order_by(Order.number.desc()).offset(offset).limit(limit))],'total':total,'offset':offset,'limit':limit}


@router.get('/orders/{id}')
def order_get(id:str,db:DB,who:Auth):
    result=service.view(db,owned(db,Order,id,who.workspace_account_id))
    # Live advisory inventory only on an authorized read, never in replay snapshots.
    if 'inventory.view' in who.permissions:
        parts={p.id:p for p in db.scalars(select(Part).where(Part.account_id==who.workspace_account_id,Part.id.in_([line['part_id'] for line in result['lines']])))}
        for line in result['lines']:
            p=parts.get(line['part_id'])
            if p:line['current_part']={'oem_number':p.oem_number,'available_quantity':p.quantity-p.reserved_quantity}
    return result


@router.patch('/orders/{id}')
def update_order(id:str,data:UpdateOrder,db:DB,who:Auth):
    return service.command(db,who.workspace_account_id,'orders:'+id+':update',data,lambda:service.update(db,service.locked_order(db,id,who.workspace_account_id),data))


@router.put('/orders/{id}/lines')
def update_lines(id:str,data:LinesInput,db:DB,who:Auth):
    return service.command(db,who.workspace_account_id,'orders:'+id+':lines',data,lambda:service.replace_lines(db,service.locked_order(db,id,who.workspace_account_id),data))


@router.post('/orders/{id}/status')
def order_status(id:str,data:OrderStatus,db:DB,who:Auth):
    return service.command(db,who.workspace_account_id,'orders:'+id+':status',data,lambda:service.change_status(db,service.locked_order(db,id,who.workspace_account_id),data.status))


@router.post('/orders/{id}/{action}')
def order_action(id:str,action:Literal['reserve','release','sell','cancel'],data:OrderAction,db:DB,who:Auth):
    return service.command(db,who.workspace_account_id,'orders:'+id+':'+action,data,lambda:service.action(db,service.locked_order(db,id,who.workspace_account_id),action))


@router.get('/orders/{id}/events')
def order_events(id:str,db:DB,who:Auth,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200)):
    owned(db,Order,id,who.workspace_account_id)
    stmt=select(OrderEvent).where(OrderEvent.account_id==who.workspace_account_id,OrderEvent.order_id==id)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=list(db.scalars(stmt.order_by(OrderEvent.created_at,OrderEvent.id).offset(offset).limit(limit)))
    actors=dict(db.execute(select(Account.id,Account.name).where(Account.id.in_({r.actor_id for r in rows}),((Account.id==who.workspace_account_id)|(Account.workspace_account_id==who.workspace_account_id)))).all()) if rows else {}
    return {'items':[{**snapshot(row),'actor_name':(row.data.get('actor_identity') or {}).get('name') or actors.get(row.actor_id)} for row in rows],'total':total,'offset':offset,'limit':limit}
