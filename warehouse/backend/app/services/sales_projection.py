"""Shared projection of existing immutable sale operations (no writes)."""
from sqlalchemy import select,or_
from app.models import Account,Vehicle,Order,OrderLine,OrderEvent
from app.services.inventory import snapshot

def project_sales(db,who,ops,*,center=False):
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
        if center:
            identity=op.after.get('actor_identity') or {}
            if identity.get('id')==op.actor_id and identity.get('name'):items[-1]['actor_name']=identity['name']
            items[-1].update(actor_id=op.actor_id,order_number=link[1].number if link else None,buyer_phone=financial.get('buyer_phone') if 'orders.view' in who.permissions else None)
    return items
