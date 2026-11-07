"""Read model for both saved plans. Counters are entries, never quantities/offers."""

import json, re, unicodedata, hashlib
from pathlib import Path
from sqlalchemy import select, func, text
from fastapi import HTTPException
from app.models import (
    Part,
    Photo,
    Operation,
    DismantlingAnnotation,
    PartNameTranslation,
    now,
)
from app.services.inventory import owned, record, snapshot
from app.services.parts_translation import translate_names, TranslationError

GLOSSARY = json.loads(
    (Path(__file__).parents[1] / "data/plan_parts_uk_glossary.json").read_text()
)


def name_key(name):
    return re.sub(
        r"\s*,\s*", ", ", " ".join(unicodedata.normalize("NFKC", name).strip().split())
    ).casefold()


def is_uk(name):
    return bool(name and re.search("[А-Яа-яІіЇїЄєҐґ]", name))


def entries(db, who, v, source):
    parts = list(
        db.scalars(
            select(Part).where(
                Part.account_id == who.workspace_account_id,
                Part.vehicle_id == v.id,
                Part.archived.is_(False),
            )
        )
    )
    byid = {p.id: p for p in parts}
    if source == "professional":
        from app.api.plan_parts import saved_workspace

        w = saved_workspace(who=who, db=db, vehicle_id=v.id)
        rs = {r["pt_id"]: r for r in w["receipts"]}
        result = []
        for c in w["categories"]:
            marker = f"plan.parts:ktype={v.ktype};pt_id={c['pt_id']}"
            ps = [p for p in parts if p.compatibility_notes == marker]
            result.append(
                dict(
                    key=f"pp:{v.ktype}:{c['pt_id']}",
                    original=c["name"],
                    manual_name=c["name_uk"],
                    category=c["classification"]["section"] or "Потребують уточнення",
                    position="",
                    pt_id=c["pt_id"],
                    parts=ps,
                    receipt=rs.get(c["pt_id"]),
                    included=not ps or any(p.assortment_enabled for p in ps),
                    base_state="planned",
                )
            )
    else:
        from app.services.virtual_inventory import listing

        w = listing(db, v)
        result = []
        for i in w["items"]:
            ps = [byid[i["part_id"]]] if i["part_id"] in byid else []
            marker = ps[0].compatibility_notes if ps else ""
            match = re.fullmatch(r"plan.parts:ktype=(\d+);pt_id=(\d+)", marker)
            result.append(
                dict(
                    key="base:" + i["id"],
                    original=i["name"],
                    manual_name="",
                    category=i["category"],
                    position=i["position"],
                    pt_id=int(match[2]) if match and int(match[1]) == v.ktype else None,
                    parts=ps,
                    receipt=None,
                    included=i["included"],
                    base_state=(
                        "dismantled"
                        if i["operational_state"] == "dismantled"
                        else "planned"
                    ),
                )
            )
    return result


def read(db, who, v, source):
    rows = entries(db, who, v, source)
    annotations = {
        a.entry_key: a
        for a in db.scalars(
            select(DismantlingAnnotation).where(
                DismantlingAnnotation.account_id == who.workspace_account_id,
                DismantlingAnnotation.vehicle_id == v.id,
            )
        )
    }
    translations = (
        {
            a.source_key: a
            for a in db.scalars(
                select(PartNameTranslation).where(
                    PartNameTranslation.account_id == who.workspace_account_id,
                    PartNameTranslation.source_key.in_(
                        [name_key(r["original"]) for r in rows]
                    ),
                )
            )
        }
        if rows
        else {}
    )
    # Receipt is historical evidence. Assumed on-vehicle quantity is NOT a receipt.
    received = set(
        db.scalars(
            select(Operation.part_id).where(
                Operation.account_id == who.workspace_account_id,
                Operation.vehicle_id == v.id,
                Operation.type == "receipt",
            )
        )
    )
    sold = set(
        db.scalars(
            select(Operation.part_id).where(
                Operation.account_id == who.workspace_account_id,
                Operation.vehicle_id == v.id,
                Operation.type == "sale",
            )
        )
    )
    photos = set(
        db.scalars(
            select(Photo.part_id)
            .join(Part, Photo.part_id == Part.id)
            .where(
                Photo.account_id == who.workspace_account_id, Part.vehicle_id == v.id
            )
        )
    )
    output = []
    for r in rows:
        a = annotations.get(r["key"])
        t = translations.get(name_key(r["original"]))
        dictionary = GLOSSARY.get(name_key(r["original"]))
        manual = (
            a.name_uk
            if a and a.name_uk
            else r["manual_name"] if is_uk(r["manual_name"]) else None
        )
        display = manual or dictionary or (t.translated if t else None) or r["original"]
        ps = r["parts"]
        hidden = bool(a and a.hidden) or not r["included"]
        stocked = any(
            p.id in received
            or (p.physical_location_kind == "on_shelf" and p.quantity > 0)
            for p in ps
        )
        state = (
            "hidden"
            if hidden
            else (
                "sold"
                if ps and all(p.quantity == 0 and p.id in sold for p in ps)
                else (
                    "received"
                    if stocked and any(p.quantity > 0 for p in ps)
                    else (
                        "empty"
                        if ps and all(p.quantity == 0 for p in ps)
                        else (
                            "dismantled"
                            if a and a.dismantled or r["base_state"] == "dismantled"
                            else "planned"
                        )
                    )
                )
            )
        )
        output.append(
            dict(
                key=r["key"],
                original=r["original"],
                name=display,
                translated=bool(manual or dictionary or t or is_uk(r["original"])),
                name_source=(
                    "manual"
                    if manual
                    else "glossary" if dictionary else t.method if t else "original"
                ),
                position=r["position"],
                category=r["category"],
                pt_id=r["pt_id"],
                state=state,
                received=stocked,
                with_photo=any(p.id in photos for p in ps),
                receipt=r["receipt"],
                parts=[
                    {**snapshot(p), "available_quantity": p.available_quantity}
                    for p in ps
                ],
            )
        )
    n = len(output)
    r = sum(i["received"] for i in output)
    return dict(
        vehicle_id=v.id,
        source=source,
        ktype=v.ktype,
        items=output,
        progress=dict(
            planned=n,
            received=r,
            with_photo=sum(i["with_photo"] for i in output),
            percent=round(100 * r / n, 1) if n else 0,
            unit="plan_entries",
        ),
        translation=dict(
            translated=sum(i["translated"] for i in output),
            pending=sum(not i["translated"] for i in output),
        ),
    )


def annotate(db, who, v, source, keys, action, name=None):
    rows = {r["key"]: r for r in entries(db, who, v, source)}
    if not set(keys) <= rows.keys():
        raise HTTPException(404, "Позицію власного плану не знайдено")
    if action == "restore" and any(not rows[k]["included"] for k in keys):
        raise HTTPException(
            409,
            "Позицію виключено у складському обліку. Відновіть її через складську картку.",
        )
    if action == "dismantled":
        states = {r["key"]: r["state"] for r in read(db, who, v, source)["items"]}
        if any(states[k] not in ("planned", "dismantled") for k in keys):
            raise HTTPException(
                409,
                "Оприбутковані, продані або приховані позиції не переводяться назад у демонтаж",
            )
    for key in keys:
        r = rows[key]
        a = db.scalar(
            select(DismantlingAnnotation)
            .where(
                DismantlingAnnotation.account_id == who.workspace_account_id,
                DismantlingAnnotation.vehicle_id == v.id,
                DismantlingAnnotation.entry_key == key,
            )
            .with_for_update()
        )
        if not a:
            a = DismantlingAnnotation(
                account_id=who.workspace_account_id,
                vehicle_id=v.id,
                entry_key=key,
                actor_id=who.actor_id,
                hidden=False,
                dismantled=False,
            )
        before = snapshot(a) if a.id else {}
        desired = (
            {"hidden": True}
            if action == "hide"
            else (
                {"hidden": False}
                if action == "restore"
                else (
                    {"dismantled": True}
                    if action == "dismantled"
                    else {"name_uk": name}
                )
            )
        )
        if all(getattr(a, k) == value for k, value in desired.items()):
            continue
        for k, value in desired.items():
            setattr(a, k, value)
        a.actor_id = who.actor_id
        a.updated_at = now()
        db.add(a)
        db.flush()
        record(
            db,
            who.workspace_account_id,
            a,
            "dismantling_annotation",
            "Явна зміна плану; залишки та фінанси не змінені",
            before,
        ).vehicle_id = v.id
    db.commit()


def translate_batch(db, who, v, source, keys):
    rows = {r["key"]: r for r in entries(db, who, v, source)}
    if not set(keys) <= rows.keys():
        raise HTTPException(404, "Позицію власного плану не знайдено")
    lock = int(
        hashlib.sha256(
            ("translation:" + who.workspace_account_id).encode()
        ).hexdigest()[:15],
        16,
    )
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock}):
        raise HTTPException(409, "Переклад уже виконується; збережені назви доступні")
    annotations = {
        a.entry_key: a
        for a in db.scalars(
            select(DismantlingAnnotation).where(
                DismantlingAnnotation.account_id == who.workspace_account_id,
                DismantlingAnnotation.vehicle_id == v.id,
            )
        )
    }
    pending = []
    pending_keys = set()
    saved = 0
    for key in keys:
        r = rows[key]
        original = r["original"]
        normal = name_key(original)
        if (
            is_uk(r["manual_name"])
            or is_uk(original)
            or (annotations.get(key) and annotations[key].name_uk)
        ):
            continue
        existing = db.scalar(
            select(PartNameTranslation).where(
                PartNameTranslation.account_id == who.workspace_account_id,
                PartNameTranslation.source_key == normal,
            )
        )
        if existing:
            continue
        if normal in GLOSSARY:
            db.add(
                PartNameTranslation(
                    account_id=who.workspace_account_id,
                    source_key=normal,
                    original=original,
                    translated=GLOSSARY[normal],
                    method="glossary",
                )
            )
            db.flush()
            saved += 1
        elif normal not in pending_keys:
            pending.append(original)
            pending_keys.add(normal)
    try:
        result = (
            translate_names(pending)
            if pending
            else {"configured": True, "translations": {}, "untranslated": []}
        )
    except TranslationError as exc:
        raise HTTPException(exc.code, str(exc)) from None
    for original, translated in result["translations"].items():
        if not is_uk(translated) or len(translated) > 400:
            continue
        db.add(
            PartNameTranslation(
                account_id=who.workspace_account_id,
                source_key=name_key(original),
                original=original,
                translated=translated,
                method="deepl",
            )
        )
        saved += 1
    db.commit()
    return dict(
        saved=saved,
        configured=result["configured"],
        untranslated=result["untranslated"],
    )
