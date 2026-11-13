"""One donor lock, preflight all rows, one transaction, no paid lookups."""

from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Part, Account
from app.services import checklists
from app.services.source_types import Resolver, MARKER
from app.services.inventory import record, stock
from app.schemas import StockInput


def add(db, who, donor, items, client):
    stored = checklists.stored_categories(
        db, donor.id, who.workspace_account_id, donor.ktype
    )
    if stored:
        types = {r.pt_id: r.name_en for r in stored}
    else:
        types = {
            r.pt_id: getattr(r, "name", "")
            for r in client.recover_categories(who.workspace_account_id, donor.ktype)
        }
    if len({i.pt_id for i in items}) != len(items) or any(
        i.ktype != donor.ktype or i.pt_id not in types for i in items
    ):
        raise HTTPException(
            422,
            "Типи повинні бути у збереженому списку вибраної модифікації; дублікати не дозволені",
        )
    resolver = Resolver(db, who.workspace_account_id)
    existing = list(
        db.scalars(
            select(Part)
            .where(
                Part.account_id == who.workspace_account_id, Part.vehicle_id == donor.id
            )
            .with_for_update()
        )
    )
    bymarker, bytype = {}, {}
    for p in existing:
        bymarker.setdefault(p.compatibility_notes, p)
        match = MARKER.fullmatch(p.compatibility_notes or "")
        if match:
            bytype.setdefault(int(match[2]), []).append(p)
    results = []
    new = []
    for item in items:
        marker = f"plan.parts:ktype={donor.ktype};pt_id={item.pt_id}"
        candidates = bytype.get(item.pt_id, [])
        old = bymarker.get(marker) or (candidates[0] if len(candidates) == 1 else None)
        if candidates and not old:
            results.append(
                {
                    "pt_id": item.pt_id,
                    "ok": True,
                    "created": False,
                    "received": False,
                    "part_id": None,
                    "part_ids": [p.id for p in candidates],
                    "quantity": None,
                    "skipped": True,
                    "review_required": True,
                }
            )
            continue
        if old:
            # Sold/zero-stock/archived entries never receive another unit via retry.
            results.append(
                {
                    "pt_id": item.pt_id,
                    "ok": True,
                    "created": False,
                    "received": False,
                    "part_id": old.id,
                    "quantity": old.quantity,
                    "name": old.name,
                    "skipped": True,
                    "review_required": old.compatibility_notes != marker
                    or old.archived,
                }
            )
            continue
        name = item.ukrainian_name.strip()
        if len(name) < 2 or len(name) > 200:
            raise HTTPException(422, "Некоректна назва деталі")
        d = resolver.resolve(item.pt_id, types[item.pt_id], name)
        p = Part(
            id=str(uuid4()),
            account_id=who.workspace_account_id,
            vehicle_id=donor.id,
            name=name,
            category_id=d.get("category_id"),
            subcategory_id=d.get("subcategory_id"),
            inventory_origin="manual",
            quantity_basis="verified",
            physical_location_kind="on_vehicle",
            availability="unchecked",
            condition="unknown",
            quantity=0,
            compatibility_notes=marker,
            description="Вибрано власником зі збереженого каталогу. Оригінальна назва: "
            + types[item.pt_id]
            + ". Сумісність перевіряється окремо.",
        )
        db.add(p)
        new.append((p, item, d))
        bymarker[marker] = p
        resolver.persist(item.pt_id, types[item.pt_id], d)
    # Assign defaults once so before/after snapshots remain complete without per-row flush.
    db.flush()
    actor = db.get(Account, db.info.get("actor_id", who.workspace_account_id))
    db.info['fresh_unassembled_receipts']=frozenset(p.id for p,_,_ in new)
    try:
        with db.no_autoflush:
            for p, item, d in new:
                record(
                    db,
                    who.workspace_account_id,
                    p,
                    "part_create",
                    "Вибрану позицію додано пакетно",
                    {},
                    flush_before=False,
                )
                stock(
                    db,
                    p,
                    StockInput(
                        type="receipt",
                        quantity=1,
                        reason="Явне пакетне додавання деталі: 1 шт.",
                    ),
                    who.workspace_account_id,
                    flush_before=False,
                )
                results.append(
                    {
                        "pt_id": item.pt_id,
                        "ok": True,
                        "created": True,
                        "received": True,
                        "part_id": p.id,
                        "quantity": 1,
                        "name": p.name,
                        "classification": d,
                    }
                )
    finally:
        db.info.pop('fresh_unassembled_receipts',None)
    db.commit()
    bytype = {r["pt_id"]: r for r in results}
    return {
        "results": [bytype[i.pt_id] for i in items],
        "completed": len(results),
        "attempted": len(items),
        "requested": len(items),
        "added": len(new),
        "skipped": len(items) - len(new),
        "errors": 0,
        "review_required": sum(bool(r.get("review_required")) for r in results),
    }
