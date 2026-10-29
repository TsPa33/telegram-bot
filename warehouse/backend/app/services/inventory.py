from decimal import Decimal
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import Category, Operation, Part, Vehicle, Account, VehicleChecklistItem, DismantlingItem


def owned(db, model, id, account_id, *, lock=False, active=False):
    if lock and model is Vehicle:
        # Donor writers take the workspace lock before vehicle/part locks.
        db.scalar(select(Account).where(Account.id==account_id).with_for_update(key_share=True))
    stmt = select(model).where(model.id == id, model.account_id == account_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None or (active and row.archived):
        raise HTTPException(404, "Запис не знайдено")
    return row


def snapshot(row):
    result = {}
    for c in row.__table__.columns:
        value = getattr(row, c.name)
        result[c.name] = (
            str(value) if isinstance(value, (Decimal, date, datetime)) else value
        )
    return result


def record(db, account_id, row, type, reason, before, *, after_extra=None, flush_before=True):
    # Batch callers must flush assigned IDs/defaults before deferring audit inserts.
    if flush_before:db.flush()
    actor=db.get(Account,db.info.get('actor_id',account_id))
    operation = Operation(
        account_id=account_id, actor_id=db.info.get("actor_id",account_id),
        part_id=row.id if isinstance(row, Part) else None,
        vehicle_id=row.vehicle_id if isinstance(row, (Part, VehicleChecklistItem, DismantlingItem)) else row.id if isinstance(row, Vehicle) else None,
        entity_id=row.id, entity_type=row.__tablename__, type=type, reason=reason,
        before=before, after={**snapshot(row), **(after_extra or {}), 'actor_identity':{'id':actor.id,'name':actor.name,'role':actor.role} if actor else None},
    )
    db.add(operation)
    return operation


def validate_part_links(db, data, account_id):
    if data.vehicle_id:
        owned(db, Vehicle, data.vehicle_id, account_id, active=True)
    if data.category_id:
        owned(db, Category, data.category_id, account_id, active=True)
    if data.subcategory_id:
        sub = owned(db, Category, data.subcategory_id, account_id, active=True)
        if not data.category_id or sub.parent_id != data.category_id:
            raise HTTPException(422, "Підкатегорія не належить вибраній категорії")


def stock(db, row, data, account_id, *, reservation_id=None, return_operation=False, sale_context=None):
    if row.archived:
        raise HTTPException(409, "Спершу відновіть запчастину з архіву")
    if data.type not in ('receipt','write_off','sale','reserve','release','correction','transfer','virtual_activation'):
        raise HTTPException(422, 'Невідома складська операція')
    if data.type in ('sale','reserve') and not row.assortment_enabled:
        raise HTTPException(409, 'Деталь виключено з асортименту')
    if data.type == 'virtual_activation':
        if row.inventory_origin!='virtual_donor' or row.activation_operation_id or row.quantity or data.quantity!=1:
            raise HTTPException(409, 'Повторна віртуальна активація заборонена')
    before = snapshot(row)
    q = data.quantity
    if data.type in ("receipt", "virtual_activation"):
        row.quantity += q
    elif data.type in ("write_off", "sale"):
        row.quantity -= q
    elif data.type == "reserve":
        row.reserved_quantity += q
    elif data.type == "release":
        # Part is already locked by every caller. Only the owning order service
        # can release an assigned reservation; legacy/manual reserves stay usable.
        from app.models import OrderReservation
        protected=db.scalar(select(func.coalesce(func.sum(OrderReservation.quantity),0)).where(
            OrderReservation.account_id==account_id,OrderReservation.part_id==row.id,OrderReservation.state=='active'))
        allowance=row.reserved_quantity-protected
        if reservation_id:
            reservation=db.get(OrderReservation,reservation_id)
            if not reservation or reservation.account_id!=account_id or reservation.part_id!=row.id or reservation.state!='active' or reservation.quantity!=q:
                raise HTTPException(409,'Некоректний резерв замовлення')
            allowance+=reservation.quantity
        if q>allowance:raise HTTPException(409,'Цей резерв належить замовленню; зніміть його через замовлення')
        row.reserved_quantity -= q
    elif data.type == "correction":
        row.quantity = q
    elif data.type == "transfer":
        row.location = data.location
        if getattr(data,"physical_location_kind",None) is not None:row.physical_location_kind=data.physical_location_kind
    if row.quantity < 0 or not 0 <= row.reserved_quantity <= row.quantity:
        raise HTTPException(409, "Недостатній залишок або некоректний резерв")
    if row.individually_tracked and row.quantity > 1:
        raise HTTPException(409, "Індивідуальна позиція може мати не більше 1 одиниці")
    if data.type in ("receipt", "correction", "sale", "write_off"):
        row.availability = "present" if row.quantity else "absent"
    sale_snapshot = None
    if data.type == "sale" and data.sale_price is not None:
        donor = db.get(Vehicle, row.vehicle_id) if row.vehicle_id else None
        actor = db.get(Account, db.info.get("actor_id",account_id))
        # Commercial snapshot lives in the existing immutable sale operation.
        # Never infer actual proceeds from the mutable Part.selling_price.
        sale_snapshot = {
            "version": 1, "source": "quick", "quantity": q,
            "unit_price": format(data.sale_price, '.2f'), "currency": data.sale_currency,
            "total": format(data.sale_price * q, '.2f'),
            "actor_name": actor.name if actor else None,
            "donor": {k: getattr(donor, k) for k in ('manufacturer','model','year','number')} if donor else None,
        }
        sale_snapshot.update(sale_context or {})
    operation=record(db, account_id, row, data.type, data.reason, before,
        after_extra={"sale":sale_snapshot} if sale_snapshot else None)
    return operation if return_operation else row


def import_categories(db, payload, account_id, *, dry_run=False):
    # Serialize imports for one account, including simultaneous first imports.
    db.scalar(select(Account).where(Account.id == account_id).with_for_update())
    nodes = {n.key: n for n in payload.nodes}
    if len(nodes) != len(payload.nodes):
        raise HTTPException(422, "Повторний стабільний ключ у файлі")
    ordered, pending = [], dict(nodes)
    resolved = set()
    depths = {}
    while pending:
        ready = [
            n
            for n in pending.values()
            if n.parent_key is None or n.parent_key in resolved
        ]
        if not ready:
            raise HTTPException(422, "Цикл або відсутній батьківський ключ")
        for n in ready:
            if n.parent_key and nodes[n.parent_key].kind == "part":
                raise HTTPException(422, "Запчастина не може мати дочірні категорії")
            depths[n.key] = depths.get(n.parent_key, 0) + 1
            if depths[n.key] > 32:
                raise HTTPException(422, "Максимальна глибина ієрархії — 32 рівні")
            ordered.append(n)
            resolved.add(n.key)
            del pending[n.key]
    existing = {
        c.external_key: c
        for c in db.scalars(
            select(Category).where(
                Category.account_id == account_id, Category.source == payload.source
            )
        )
    }
    new_count = sum(n.key not in existing for n in ordered)
    if dry_run:
        return {
            "created": new_count,
            "existing": len(ordered) - new_count,
            "total": len(ordered),
        }
    mapping = dict(existing)
    for n in ordered:
        parent_id = mapping[n.parent_key].id if n.parent_key else None
        if n.key in existing:
            old = existing[n.key]
            if (old.parent_id, old.name, old.kind) != (parent_id, n.name, n.kind):
                raise HTTPException(
                    409,
                    "Стабільний ключ вже має іншу назву або ієрархію; використайте нове джерело",
                )
        else:
            row = Category(
                account_id=account_id,
                name=n.name,
                parent_id=parent_id,
                kind=n.kind,
                source=payload.source,
                external_key=n.key,
            )
            db.add(row)
            db.flush()
            mapping[n.key] = row
            record(
                db, account_id, row, "category_import", f"Імпорт: {payload.source}", {}
            )
    return {
        "created": new_count,
        "existing": len(ordered) - new_count,
        "total": len(ordered),
    }


def checklist(db, vehicle_id, account_id):
    vehicle = owned(db, Vehicle, vehicle_id, account_id, lock=True, active=True)
    categories = list(
        db.scalars(select(Category).where(Category.account_id == account_id))
    )
    by_id = {c.id: c for c in categories}

    def active_chain(c):
        while c:
            if c.archived:
                return False
            c = by_id.get(c.parent_id)
        return True

    leaves = [c for c in categories if c.kind == "part" and active_chain(c)]
    if not leaves:
        raise HTTPException(
            409,
            "Спочатку імпортуйте категорії із запчастинами. Вихідний каталог не постачається",
        )
    exists = set(
        db.scalars(
            select(Part.checklist_category_id).where(
                Part.vehicle_id == vehicle.id, Part.account_id == account_id
            )
        )
    )
    created = 0
    for c in leaves:
        if c.id in exists:
            continue
        row = Part(
            account_id=account_id,
            name=c.name,
            category_id=c.parent_id or c.id,
            vehicle_id=vehicle.id,
            checklist_category_id=c.id,
            quantity=0,
            reserved_quantity=0,
            availability="unchecked",
        )
        db.add(row)
        record(
            db,
            account_id,
            row,
            "checklist_create",
            "Стандартний список можливих запчастин, не OEM-каталог",
            {},
        )
        created += 1
    return {"created": created, "existing": len(leaves) - created}
