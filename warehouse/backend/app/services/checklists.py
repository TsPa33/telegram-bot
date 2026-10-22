"""Account-local donor checklists, independent of stock and global taxonomy."""
from fastapi import HTTPException
from sqlalchemy import select, func

from app.models import Vehicle, VehicleChecklistItem, now
from app.services.inventory import owned, record, snapshot


def generate(db, vehicle_id, account_id, client, *, refresh=False):
    # Same lock as vehicle editing: concurrent first imports cannot pay twice,
    # or attach an in-flight result to a subsequently changed K-Type.
    vehicle = owned(db, Vehicle, vehicle_id, account_id, lock=True, active=True)
    if vehicle.ktype is None:
        raise HTTPException(409, "Спочатку виберіть і збережіть конкретний K-Type автомобіля")
    existing = {row.pt_id: row for row in db.scalars(select(VehicleChecklistItem).where(
        VehicleChecklistItem.vehicle_id == vehicle.id,
        VehicleChecklistItem.account_id == account_id,
        VehicleChecklistItem.source == "plan.parts",
        VehicleChecklistItem.ktype == vehicle.ktype,
    ))}
    if not refresh and (existing or (vehicle.checklist_ktype == vehicle.ktype and vehicle.checklist_synced_at)):
        return {"created": 0, "updated": 0, "existing": len(existing), "total": len(existing), "provider_requested": False}
    rows = client.categories(account_id, vehicle.ktype)
    before = snapshot(vehicle)
    synced = now()
    created = updated = 0
    for provider in rows:
        row = existing.get(provider.pt_id)
        if row is None:
            row = VehicleChecklistItem(account_id=account_id, vehicle_id=vehicle.id,
                source="plan.parts", ktype=vehicle.ktype, pt_id=provider.pt_id,
                name_en=provider.name, article_count=provider.article_count, last_synced_at=synced)
            db.add(row)
            created += 1
        else:
            updated += int((row.name_en, row.article_count) != (provider.name, provider.article_count))
            row.name_en = provider.name
            row.article_count = provider.article_count
            row.last_synced_at = synced
            # Never reset status, Ukrainian name or notes. Missing types remain.
    vehicle.checklist_ktype = vehicle.ktype
    vehicle.checklist_synced_at = synced
    record(db, account_id, vehicle, "plan_parts_checklist_import",
           f"Plan.Parts, K-Type {vehicle.ktype}: нових {created}, оновлено {updated}; не складські залишки", before)
    return {"created": created, "updated": updated, "existing": len(existing),
            "total": len(existing) + created, "returned": len(rows), "provider_requested": True}


def listing(db, vehicle_id, account_id, *, offset=0, limit=100, include_history=False):
    vehicle = owned(db, Vehicle, vehicle_id, account_id)
    base = select(VehicleChecklistItem).where(VehicleChecklistItem.account_id == account_id,
                                            VehicleChecklistItem.vehicle_id == vehicle.id)
    current = base.where(VehicleChecklistItem.ktype == vehicle.ktype)
    total_all = db.scalar(select(func.count()).select_from(base.subquery()))
    current_rows = current.subquery()
    current_count, current_sync = db.execute(select(func.count(), func.max(current_rows.c.last_synced_at)).select_from(current_rows)).one()
    selected = base if include_history else current
    total = db.scalar(select(func.count()).select_from(selected.subquery()))
    return {"items": [snapshot(row) for row in db.scalars(selected.order_by(VehicleChecklistItem.name_en, VehicleChecklistItem.id).offset(offset).limit(limit))],
            "total": total, "offset": offset, "limit": limit, "historical_total": total_all - current_count,
            "ktype": vehicle.ktype, "synced": bool(current_count) or (vehicle.checklist_ktype == vehicle.ktype and vehicle.checklist_synced_at is not None),
            "synced_at": current_sync or (vehicle.checklist_synced_at if vehicle.checklist_ktype == vehicle.ktype else None)}


def update(db, vehicle_id, item_id, account_id, changes):
    vehicle = owned(db, Vehicle, vehicle_id, account_id, lock=True, active=True)
    row = db.scalar(select(VehicleChecklistItem).where(VehicleChecklistItem.id == item_id,
        VehicleChecklistItem.vehicle_id == vehicle.id, VehicleChecklistItem.account_id == account_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Пункт перевірки не знайдено")
    if row.ktype != vehicle.ktype:
        raise HTTPException(409, "Попередній K-Type доступний лише для перегляду")
    before = snapshot(row)
    for key, value in changes.items():
        setattr(row, key, value)
    record(db, account_id, row, "checklist_update", "Оновлено перевірку потенційної деталі; залишки не змінено", before)
    return snapshot(row)
