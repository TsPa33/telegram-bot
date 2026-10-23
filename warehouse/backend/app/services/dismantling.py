"""Local donor workflow. Only an explicit receipt calls the existing stock ledger."""
import json
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func

from app.models import Account, Category, DismantlingItem, Operation, Part, Vehicle, now
from app.schemas import StockInput
from app.services.inventory import owned, record, snapshot, stock

CATALOG = json.loads((Path(__file__).resolve().parents[1] / "data/dismantling_catalog.json").read_text())


def start(db, vehicle_id, account_id):
    vehicle = owned(db, Vehicle, vehicle_id, account_id, lock=True, active=True)
    existing = set(db.scalars(select(DismantlingItem.catalog_key).where(
        DismantlingItem.vehicle_id == vehicle_id, DismantlingItem.account_id == account_id,
        DismantlingItem.source == CATALOG['version'])))
    before = snapshot(vehicle)
    created = 0
    for category in CATALOG['categories']:
        for sub in category['subcategories']:
            for key, name, position in sub['parts']:
                if key in existing:
                    continue
                db.add(DismantlingItem(account_id=account_id, vehicle_id=vehicle_id,
                    source=CATALOG['version'], catalog_key=key, category_key=category['key'],
                    category_name=category['name'], subcategory_key=sub['key'],
                    subcategory_name=sub['name'], name=name, position=position))
                created += 1
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


def receipt(db, row, data, account_id):
    # Durable workflow marker, independent of current stock, sale, archive or reload.
    if row.received_at is not None:
        return False
    if row.status == 'absent':
        raise HTTPException(409, 'Відсутню деталь не можна оприбуткувати. Спочатку підтвердьте демонтаж.')
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
    if data.action != 'receipt' and any(row.received_at is not None for row in rows):
        raise HTTPException(409, 'Уже оприбутковані деталі змінюйте через складські операції.')
    if data.action == 'receipt' and any(row.status == 'absent' and row.received_at is None for row in rows):
        raise HTTPException(409, 'Серед вибраних є відсутня деталь. Спочатку підтвердьте демонтаж.')
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
