"""One transaction per command. Lock order: account NO KEY UPDATE, order, sorted parts.

NO KEY UPDATE permits FK key-share checks from legacy part-only writers, avoiding
an account/part lock inversion. Stock quantities are mutated only through stock().
"""
import hashlib
import json
from decimal import Decimal
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from app.models import Account, Buyer, Order, OrderLine, OrderReservation, OrderEvent, OrderRequest, Part, Vehicle, now
from app.schemas import StockInput
from app.schemas.orders import Delivery, normalize_phone
from app.services.inventory import owned, record, snapshot, stock


def lock_account(db, account_id):
    db.scalar(select(Account).where(Account.id==account_id).with_for_update(key_share=True))


def command(db, account_id, scope, data, execute):
    lock_account(db,account_id)
    fingerprint=hashlib.sha256(json.dumps({'scope':scope,'data':data.model_dump(mode='json',exclude={'request_key'})},sort_keys=True).encode()).hexdigest()
    prior=db.scalar(select(OrderRequest).where(OrderRequest.account_id==account_id,OrderRequest.request_key==data.request_key))
    if prior:
        if prior.fingerprint!=fingerprint:raise HTTPException(409,'Ідемпотентний ключ уже використано для іншого запиту')
        return prior.response
    result=execute()
    db.add(OrderRequest(account_id=account_id,request_key=data.request_key,fingerprint=fingerprint,response=result))
    db.commit()
    return result


def buyer_values(data):
    return {**data.model_dump(),'phone_normalized':normalize_phone(data.phone),
            'additional_phone_normalized':normalize_phone(data.additional_phone) if data.additional_phone else ''}


def save_buyer(db,account_id,data,id=None):
    row=owned(db,Buyer,id,account_id,lock=True) if id else Buyer(account_id=account_id)
    before=snapshot(row) if id else {}
    for key,value in buyer_values(data).items():setattr(row,key,value)
    row.updated_at=now();db.add(row)
    record(db,account_id,row,'buyer_update' if id else 'buyer_create','Дані покупця',before)
    db.commit();return snapshot(row)


def lines(db,order):
    return list(db.scalars(select(OrderLine).where(OrderLine.order_id==order.id,OrderLine.account_id==order.account_id,OrderLine.active).order_by(OrderLine.id)))


def reservations(db,order):
    return list(db.scalars(select(OrderReservation).join(OrderLine,OrderLine.id==OrderReservation.order_line_id).where(
        OrderLine.order_id==order.id,OrderReservation.account_id==order.account_id,OrderReservation.state=='active').order_by(OrderReservation.part_id)))


def view(db,order):
    active_lines=lines(db,order);totals={}
    for line in active_lines:totals[line.currency]=totals.get(line.currency,Decimal('0.00'))+line.line_total
    return {**snapshot(order),'lines':[snapshot(line) for line in active_lines],
            'reservations':[snapshot(r) for r in reservations(db,order)],
            'totals_by_currency':{currency:format(value,'.2f') for currency,value in sorted(totals.items())}}


def event(db,order,type,data):
    order.updated_at=now()
    db.add(OrderEvent(account_id=order.account_id,order_id=order.id,actor_id=order.account_id,type=type,data=data))


def status(db,order,value):
    if order.status!=value:
        event(db,order,'status_changed',{'before':order.status,'after':value});order.status=value


def lock_parts(db,account_id,ids):
    return {id:owned(db,Part,id,account_id,lock=True,active=True) for id in sorted(set(ids))}


def insert_lines(db,order,data,parts):
    for item in data:
        part=parts[item.part_id]
        donor=owned(db,Vehicle,part.vehicle_id,order.account_id) if part.vehicle_id else None
        db.add(OrderLine(account_id=order.account_id,order_id=order.id,part_id=part.id,name=part.name,
            donor_snapshot={key:getattr(donor,key) for key in ('id','manufacturer','model','year','number')} if donor else {},
            quantity=item.quantity,unit_price=item.unit_price,currency=item.currency,line_total=item.unit_price*item.quantity))
    db.flush()


def create(db,account_id,data):
    buyer=owned(db,Buyer,data.buyer_id,account_id)
    parts=lock_parts(db,account_id,[item.part_id for item in data.lines])
    number=(db.scalar(select(func.max(Order.number)).where(Order.account_id==account_id)) or 0)+1
    values={key:getattr(data,key) for key in Delivery.model_fields if key not in ('contact_name','contact_phone')}
    order=Order(account_id=account_id,number=number,buyer_id=buyer.id,contact_name=data.contact_name or buyer.name,
        contact_phone=data.contact_phone or buyer.phone,contact_phone_normalized=normalize_phone(data.contact_phone or buyer.phone),**values)
    db.add(order);db.flush();insert_lines(db,order,data.lines,parts)
    event(db,order,'created',{'order':view(db,order)});db.flush();return view(db,order)


def locked_order(db,id,account_id):return owned(db,Order,id,account_id,lock=True)


def update(db,order,data):
    if order.status in ('cancelled','completed'):raise HTTPException(409,'Замовлення закрите')
    before=snapshot(order);changes=data.model_dump(exclude_unset=True,exclude={'request_key'})
    if 'buyer_id' in changes:
        if order.sold_at:raise HTTPException(409,'Не можна змінити покупця підтвердженого продажу')
        buyer=owned(db,Buyer,changes['buyer_id'],order.account_id)
        changes.setdefault('contact_name',buyer.name);changes.setdefault('contact_phone',buyer.phone)
    merged={key:changes.get(key,getattr(order,key)) for key in Delivery.model_fields}
    try:Delivery.model_validate(merged)
    except ValidationError:raise HTTPException(422,'Для доставки вкажіть місто та відділення або адресу') from None
    for key,value in changes.items():setattr(order,key,value)
    if 'contact_phone' in changes:order.contact_phone_normalized=normalize_phone(order.contact_phone)
    event(db,order,'updated',{'before':before,'after':snapshot(order)});db.flush();return view(db,order)


def replace_lines(db,order,data):
    if order.sold_at or order.status!='new' or reservations(db,order):raise HTTPException(409,'Спочатку зніміть резерв; продані або закриті позиції незмінні')
    before=[snapshot(line) for line in lines(db,order)]
    parts=lock_parts(db,order.account_id,[item.part_id for item in data.lines])
    for line in lines(db,order):line.active=False
    db.flush();insert_lines(db,order,data.lines,parts)
    event(db,order,'lines_changed',{'before':before,'after':[snapshot(line) for line in lines(db,order)]})
    return view(db,order)


def move_stock(db,part,order,type,quantity,reservation=None):
    operation=stock(db,part,StockInput(type=type,quantity=quantity,reason=f'Замовлення №{order.number}'),order.account_id,
        reservation_id=reservation.id if reservation else None,return_operation=True)
    db.flush();return operation.id


def action(db,order,kind):
    active_lines=lines(db,order)
    if kind=='cancel' and order.status=='cancelled':return view(db,order)
    if order.sold_at or order.status in ('completed','cancelled'):raise HTTPException(409,'Продаж уже підтверджено або замовлення закрите')
    active=reservations(db,order)
    parts=lock_parts(db,order.account_id,[r.part_id for r in active] if kind in ('release','cancel') else [line.part_id for line in active_lines])
    operations=[]
    if kind=='reserve':
        if order.status!='new' or active:raise HTTPException(409,'Позиції вже зарезервовано або відправлено')
        for line in active_lines:
            part=parts[line.part_id]
            op=move_stock(db,part,order,'reserve',line.quantity)
            db.add(OrderReservation(account_id=order.account_id,order_line_id=line.id,part_id=part.id,quantity=line.quantity,reserve_operation_id=op))
            operations.append(op)
        status(db,order,'reserved');event(db,order,'reserved',{'operation_ids':operations})
    elif kind in ('release','cancel'):
        if kind=='release' and order.status!='reserved':raise HTTPException(409,'Немає резерву, який можна зняти')
        for reservation in active:
            op=move_stock(db,parts[reservation.part_id],order,'release',reservation.quantity,reservation)
            reservation.release_operation_id=op;reservation.state='released';db.flush();operations.append(op)
        if active:event(db,order,'reservation_released',{'operation_ids':operations})
        status(db,order,'cancelled' if kind=='cancel' else 'new')
        if kind=='cancel':event(db,order,'cancelled',{})
    elif kind=='sell':
        by_line={r.order_line_id:r for r in active};consumed_operations=[]
        for line in active_lines:
            part=parts[line.part_id];reservation=by_line.get(line.id)
            if reservation:
                reservation.release_operation_id=move_stock(db,part,order,'release',reservation.quantity,reservation)
                consumed_operations.append(reservation.release_operation_id)
                reservation.state='consumed';db.flush()
            op=move_stock(db,part,order,'sale',line.quantity);line.sale_operation_id=op
            if reservation:reservation.sale_operation_id=op
            operations.append(op)
        if consumed_operations:event(db,order,'reservation_released',{'operation_ids':consumed_operations,'reason':'consumed_by_sale'})
        order.sold_at=now()
        event(db,order,'sale_confirmed',{'operation_ids':operations,'lines':[snapshot(line) for line in active_lines],
            'buyer_id':order.buyer_id,'contact_name':order.contact_name,'contact_phone':order.contact_phone})
    else:raise HTTPException(422,'Невідома дія')
    db.flush();return view(db,order)


def change_status(db,order,value):
    allowed=(value=='shipped' and order.status in ('new','reserved') and (order.sold_at or reservations(db,order))) or (value=='completed' and order.status=='shipped' and order.sold_at)
    if not allowed:raise HTTPException(409,'Недопустимий перехід; резервування, продаж і скасування мають окремі дії')
    status(db,order,value);db.flush();return view(db,order)
