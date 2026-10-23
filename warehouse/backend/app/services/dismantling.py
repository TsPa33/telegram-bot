"""Local donor workflow. Only an explicit receipt calls the existing stock ledger."""
import json
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_

from app.models import Account, Category, DismantlingItem, Operation, Part, Vehicle, now
from app.schemas import StockInput
from app.services.inventory import owned, record, snapshot, stock

CATALOG = json.loads((Path(__file__).resolve().parents[1] / "data/dismantling_catalog.json").read_text())


def start(db, vehicle_id, account_id):
    vehicle = owned(db, Vehicle, vehicle_id, account_id, lock=True, active=True)
    existing = set(db.execute(select(DismantlingItem.source,DismantlingItem.catalog_key).where(
        DismantlingItem.vehicle_id == vehicle_id,DismantlingItem.account_id == account_id)).all())
    before = snapshot(vehicle)
    created = 0
    from app.services.dismantling_catalog import imported_types
    types=[]
    for category in CATALOG['categories']:
        for sub in category['subcategories']:
            for key,name,position in sub['parts']:
                types.append(dict(source=CATALOG['version'],catalog_key=key,category_key=category['key'],
                    category_name=category['name'],subcategory_key=sub['key'],subcategory_name=sub['name'],name=name,position=position))
    types.extend(imported_types(db,account_id))
    for item in types:
        if (item['source'],item['catalog_key']) not in existing:
            db.add(DismantlingItem(account_id=account_id,vehicle_id=vehicle_id,**item))
            created+=1
    if vehicle.status == 'planned':
        vehicle.status = 'dismantling'
    if created or before['status'] != vehicle.status:
        record(db, account_id, vehicle, 'dismantling_start',
               f'Локальний базовий список: додано {created}; комплектацію не підтверджено', before)
    return {'created': created, 'existing': len(existing), 'status': vehicle.status}


def listing(db, vehicle_id, account_id):
    vehicle = owned(db, Vehicle, vehicle_id, account_id)
    rows = list(db.scalars(select(DismantlingItem).where(DismantlingItem.account_id == account_id,
        DismantlingItem.vehicle_id == vehicle_id).order_by(DismantlingItem.category_name,
        DismantlingItem.subcategory_name, DismantlingItem.name, DismantlingItem.position)))
    parts = {p.id:p for p in db.scalars(select(Part).where(Part.account_id == account_id, Part.vehicle_id == vehicle_id))}
    items = []
    for row in rows:
        part = parts.get(row.part_id)
        items.append({**snapshot(row), 'stock': ({**snapshot(part), 'available_quantity': part.available_quantity} if part else None)})
    sold = db.scalar(select(func.coalesce(func.sum(
        Operation.before['quantity'].as_integer() - Operation.after['quantity'].as_integer()), 0)).where(
        Operation.account_id == account_id, Operation.vehicle_id == vehicle_id, Operation.type == 'sale'))
    return {'items': items, 'status': vehicle.status, 'archived': vehicle.archived,
            'potential_positions': len(rows),
            'dismantled_positions': sum(r.status == 'dismantled' or r.received_at is not None for r in rows),
            'received_positions': sum(r.received_at is not None for r in rows),
            'stock_positions': sum(not p.archived and p.quantity > 0 for p in parts.values()),
            'stock_units': sum(p.quantity for p in parts.values() if not p.archived),
            'sold_units': sold}


def category_node(db, account_id, source, key, name, kind, parent_id=None):
    if len(key)>200:
        from hashlib import sha256
        key='key-sha256:'+sha256(key.encode()).hexdigest()
    node = db.scalar(select(Category).where(Category.account_id == account_id,
        Category.source == source, Category.external_key == key))
    if node:
        if node.archived or node.kind != kind or node.parent_id != parent_id:
            raise HTTPException(409, 'Категорію змінено або архівовано. Перевірте каталог перед оприбуткуванням.')
        return node
    node = Category(account_id=account_id, source=source, external_key=key, name=name,
                    kind=kind, parent_id=parent_id)
    db.add(node)
    record(db, account_id, node, 'category_import', 'Категорія локального розбору при явному оприбуткуванні', {})
    return node


def receipt(db, row, data, account_id, *, confirmed=False):
    # Durable workflow marker, independent of current stock, sale, archive or reload.
    if row.received_at is not None:
        return False
    if not row.included or (not confirmed and row.status != 'dismantled'):
        raise HTTPException(409, 'Оприбутковувати можна лише включені та підтверджені демонтовані деталі.')
    # Same account lock as existing category import: no duplicated category tree.
    db.scalar(select(Account).where(Account.id == account_id).with_for_update())
    root = category_node(db, account_id, row.source, 'category:'+row.category_key,
                         row.category_name, 'category')
    sub = category_node(db, account_id, row.source, 'subcategory:'+row.category_key+':'+row.subcategory_key,
                        row.subcategory_name, 'subcategory', root.id)
    name = row.name + (' · '+row.position if row.position else '')
    leaf = category_node(db, account_id, row.source, 'part:'+row.catalog_key, name, 'part', sub.id)
    part = db.scalar(select(Part).where(Part.account_id == account_id, Part.vehicle_id == row.vehicle_id,
                                      Part.checklist_category_id == leaf.id).with_for_update())
    before = snapshot(row)
    if part:
        if part.archived:
            raise HTTPException(409, 'Пов’язану складську позицію архівовано. Відновіть її у складі.')
        # Re-link a pre-existing receipt (e.g. workflow state restored separately).
        previous = db.scalar(select(Operation).where(Operation.account_id == account_id,
            Operation.part_id == part.id, Operation.type == 'receipt').order_by(Operation.created_at).limit(1))
        if previous:
            row.part_id, row.received_at, row.status = part.id, previous.created_at, 'dismantled'
            row.quantity = previous.after['quantity'] - previous.before['quantity']
            row.condition = part.condition
            record(db, account_id, row, 'dismantling_receipt', 'Знайдено вже виконане надходження; без зміни залишку', before)
            return False
        if part.quantity:
            raise HTTPException(409, 'Позиція вже має залишок. Перевірте складські операції.')
    else:
        part = Part(account_id=account_id, vehicle_id=row.vehicle_id, name=name,
                    category_id=root.id, subcategory_id=sub.id, checklist_category_id=leaf.id)
        db.add(part)
        record(db, account_id, part, 'part_create', 'Позиція розбору перед явним надходженням', {})
    part_before = snapshot(part)
    if data.condition is not None:
        part.condition = data.condition
    elif row.condition is not None:
        part.condition = row.condition
    elif row.status == 'damaged':
        part.condition = 'damaged'
    if data.location:
        part.location = data.location
    if data.selling_price is not None:
        part.selling_price = data.selling_price
    if snapshot(part) != part_before:
        record(db, account_id, part, 'part_update', 'Параметри підтвердженого надходження з розбору', part_before)
    stock(db, part, StockInput(type='receipt', quantity=data.quantity,
                              reason=f'Розбір: {row.source}/{row.catalog_key}'), account_id)
    row.part_id, row.received_at = part.id, now()
    row.status, row.quantity, row.condition = 'dismantled', data.quantity, part.condition
    record(db, account_id, row, 'dismantling_receipt', 'Явно оприбутковано через складське надходження', before)
    return True


def actions(db, vehicle_id, account_id, data):
    owned(db, Vehicle, vehicle_id, account_id, lock=True, active=True)
    rows = list(db.scalars(select(DismantlingItem).where(DismantlingItem.account_id == account_id,
        DismantlingItem.vehicle_id == vehicle_id, DismantlingItem.id.in_(data.ids))
        .order_by(DismantlingItem.id).with_for_update()))
    if len(rows) != len(data.ids):
        raise HTTPException(404, 'Пункт розбору не знайдено')
    # Validate the entire batch before changing anything; transaction covers all rows.
    if data.action == 'dismantled' and any(not row.included for row in rows):
        raise HTTPException(409,'Спочатку поверніть деталь до плану розбору')
    if data.action != 'receipt' and any(row.received_at is not None for row in rows):
        raise HTTPException(409, 'Уже оприбутковані деталі змінюйте через складські операції.')
    if data.action == 'receipt' and any((not row.included or row.status != 'dismantled') and row.received_at is None for row in rows):
        raise HTTPException(409, 'Вибрані деталі мають бути включені та підтверджені демонтованими.')
    updated = 0
    for row in rows:
        if data.action == 'receipt':
            updated += int(receipt(db, row, data, account_id))
        elif row.status != data.action:
            before = snapshot(row)
            row.status = data.action
            if data.action == 'damaged':
                row.condition = 'damaged'
            record(db, account_id, row, 'dismantling_status', 'Зміна перевірки; складський залишок не змінено', before)
            updated += 1
    return {'updated': updated, 'skipped': len(rows) - updated, 'total': len(rows)}


def scope_query(vehicle_id,account_id,*,source=None,category_key=None,subcategory_key=None,q=''):
    stmt=select(DismantlingItem).where(DismantlingItem.vehicle_id==vehicle_id,DismantlingItem.account_id==account_id)
    for name,value in [('source',source),('category_key',category_key),('subcategory_key',subcategory_key)]:
        if value is not None:stmt=stmt.where(getattr(DismantlingItem,name)==value)
    if q.strip():
        stmt=stmt.where(or_(*[func.lower(getattr(DismantlingItem,k)).contains(q.strip().lower(),autoescape=True)
                             for k in ['name','position','category_name','subcategory_name']]))
    return stmt


def selection_digest(action,ids):
    from hashlib import sha256
    return sha256((action+'|'+','.join(sorted(ids))).encode()).hexdigest()


def workspace(db,vehicle_id,account_id,*,offset=0,limit=100,visibility='all',**scope):
    vehicle=owned(db,Vehicle,vehicle_id,account_id)
    base=scope_query(vehicle_id,account_id)
    rows=base.subquery()
    totals=db.execute(select(func.count(),func.count().filter(rows.c.included),
        func.count().filter(~rows.c.included),func.count().filter(or_(rows.c.status=='dismantled',rows.c.received_at.is_not(None))),
        func.count().filter(rows.c.received_at.is_not(None))).select_from(rows)).one()
    group_cols=['source','category_key','category_name','subcategory_key','subcategory_name']
    hierarchy=[dict(zip(group_cols+['total','included'],row)) for row in db.execute(select(
        *[getattr(rows.c,k) for k in group_cols],func.count(),func.count().filter(rows.c.included))
        .select_from(rows).group_by(*[getattr(rows.c,k) for k in group_cols]).order_by(rows.c.category_name,rows.c.subcategory_name))]
    selected=scope_query(vehicle_id,account_id,**scope)
    if visibility!='all':selected=selected.where(DismantlingItem.included.is_(visibility=='included'))
    filtered=selected.subquery()
    total=db.scalar(select(func.count()).select_from(filtered))
    eligible=scope_query(vehicle_id,account_id,**scope).where(DismantlingItem.included.is_(True),DismantlingItem.received_at.is_(None)).subquery()
    mark_count,receipt_count=db.execute(select(func.count().filter(eligible.c.status!='dismantled'),
        func.count().filter(eligible.c.status=='dismantled')).select_from(eligible)).one()
    tokens={}
    for action,condition in [('receipt',eligible.c.status=='dismantled'),('dismantled',eligible.c.status!='dismantled')]:
        candidate_ids=list(db.scalars(select(eligible.c.id).where(condition).order_by(eligible.c.id).limit(1001)))
        tokens['receipt' if action=='receipt' else 'mark']=selection_digest(action,candidate_ids)
    page=list(db.scalars(selected.order_by(DismantlingItem.category_name,DismantlingItem.subcategory_name,
        DismantlingItem.name,DismantlingItem.position,DismantlingItem.id).offset(offset).limit(limit)))
    ids=[row.part_id for row in page if row.part_id]
    parts={p.id:p for p in db.scalars(select(Part).where(Part.account_id==account_id,Part.id.in_(ids)))} if ids else {}
    add_ids=list(db.scalars(scope_query(vehicle_id,account_id).with_only_columns(DismantlingItem.id).where(DismantlingItem.included.is_(True),DismantlingItem.received_at.is_(None)).order_by(DismantlingItem.id).limit(10001)))
    return {'add_count':len(add_ids),'add_token':selection_digest('add',add_ids),'contract_version':2,'items':[{**snapshot(row),'stock':snapshot(parts[row.part_id]) if row.part_id in parts else None} for row in page],
        'total':total,'offset':offset,'limit':limit,'hierarchy':hierarchy,'status':vehicle.status,'archived':vehicle.archived,
        'counts':dict(zip(['total','included','excluded','dismantled','received'],totals)),
        'scope_counts':{'mark':mark_count,'receipt':receipt_count},'scope_tokens':tokens}


def change_plan(db,vehicle_id,account_id,data):
    owned(db,Vehicle,vehicle_id,account_id,lock=True,active=True)
    stmt=scope_query(vehicle_id,account_id,source=data.source,category_key=data.category_key,subcategory_key=data.subcategory_key)
    if data.ids is not None:stmt=stmt.where(DismantlingItem.id.in_(data.ids))
    rows=list(db.scalars(stmt.order_by(DismantlingItem.id).with_for_update()))
    if data.ids is not None and len(rows)!=len(data.ids):raise HTTPException(404,'Пункт плану не знайдено')
    updated=0
    for row in rows:
        if row.included!=data.included:
            before=snapshot(row);row.included=data.included
            record(db,account_id,row,'dismantling_plan','Змінено лише план; статус і склад не змінено',before)
            updated+=1
    return {'updated':updated,'total':len(rows)}


def batch(db,vehicle_id,account_id,data):
    owned(db,Vehicle,vehicle_id,account_id,lock=True,active=True)
    stmt=scope_query(vehicle_id,account_id,source=data.source,category_key=data.category_key,subcategory_key=data.subcategory_key,q=data.q)
    stmt=stmt.where(DismantlingItem.included.is_(True),DismantlingItem.received_at.is_(None))
    stmt=stmt.where(DismantlingItem.status=='dismantled' if data.action=='receipt' else DismantlingItem.status!='dismantled')
    rows=list(db.scalars(stmt.order_by(DismantlingItem.id).limit(1001).with_for_update()))
    if len(rows)>1000:raise HTTPException(422,'Звузьте категорію або пошук: не більше 1000 деталей за одну операцію')
    if not rows:return {'updated':0,'skipped':data.expected_count,'total':0}
    if len(rows)!=data.expected_count or selection_digest(data.action,[row.id for row in rows])!=data.selection_token:raise HTTPException(409,'Вибір змінився. Оновіть список і підтвердьте кількість знову.')
    # The same transaction and row locks as v1. No hidden chunking/partial receipts.
    from types import SimpleNamespace
    action=SimpleNamespace(**{**data.model_dump(),'ids':[r.id for r in rows]})
    return actions(db,vehicle_id,account_id,action)


def add_stock(db, vehicle_id, account_id, data):
    """One explicit user confirmation is the receipt authority, never a GET/checkbox.

    Lock ordering and durable received_at marker match the legacy workflow.
    An exact selection digest rejects stale or partly changed confirmations.
    """
    owned(db, Vehicle, vehicle_id, account_id, lock=True, active=True)
    stmt=scope_query(vehicle_id, account_id).where(
        DismantlingItem.included.is_(True), DismantlingItem.received_at.is_(None))
    rows=list(db.scalars(stmt.order_by(DismantlingItem.id).limit(10001).with_for_update()))
    if len(rows)>10000:
        raise HTTPException(422, 'Не більше 10 000 нових позицій за одне підтвердження')
    if not rows:
        return {'updated':0,'skipped':data.expected_count,'total':0}
    if len(rows)!=data.expected_count or selection_digest('add',[r.id for r in rows])!=data.selection_token:
        raise HTTPException(409,'Вибір змінився. Оновіть список і підтвердьте кількість знову.')
    updated=sum(int(receipt(db,row,data,account_id,confirmed=True)) for row in rows)
    return {'updated':updated,'skipped':len(rows)-updated,'total':len(rows)}
