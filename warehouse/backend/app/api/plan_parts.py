from app.api.secure_route import SecureRoute
"""Paid lookups use POST to require the existing session and CSRF checks."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Part
from app.services import checklists
from app.services.plan_parts_classification import classify, match_existing_category
from app.db import get_db
from app.models import Vehicle
from app.services.inventory import owned, record, snapshot, stock
from app.schemas import StockInput
from app.services.parts_translation import translate_names, TranslationError

from app.api.deps import Identity, identity
from app.services.plan_parts import Brand, ModelOption, Modification, CatalogPartType, PlanPartsClient, PlanPartsError, modifications_for_year

router = APIRouter(route_class=SecureRoute,prefix="/api/v1/plan-parts", tags=["Plan.Parts"])


def plan_parts_client():
    return PlanPartsClient()


@router.post("/brands/lookup", response_model=list[Brand])
def brands(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
):
    try:
        return client.brands(who.workspace_account_id)
    except PlanPartsError as exc:
        raise HTTPException(
            exc.status, str(exc), headers={"Retry-After": str(exc.retry_after or 30)} if exc.status == 429 else None
        ) from None


@router.post("/models/lookup", response_model=list[ModelOption])
def models(who: Annotated[Identity, Depends(identity)],
           client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
           mfa_id: int = Query(gt=0)):
    try:
        return client.models(who.workspace_account_id, mfa_id)
    except PlanPartsError as exc:
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": str(exc.retry_after or 30)} if exc.status == 429 else None) from None


@router.post("/modifications/lookup", response_model=list[Modification])
def modifications(who: Annotated[Identity, Depends(identity)],
                  client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
                  ms_id: int = Query(gt=0), year: int | None = Query(default=None, ge=1886, le=2100)):
    try:
        return modifications_for_year(client.modifications(who.workspace_account_id, ms_id), year)
    except PlanPartsError as exc:
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": str(exc.retry_after or 30)} if exc.status == 429 else None) from None


@router.post("/coverage/lookup")
def vehicle_coverage_lookup(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
):
    """Owner-only opt-in count lookup. Never creates or persists stock/catalogue rows."""
    # This route uses provider-paid tokens. Until billing exists only the workspace
    # owner can trigger paid lookups; staff never receive provider details.
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Перевірка зовнішнього каталогу поки доступна лише власнику")
    donor = owned(db, Vehicle, vehicle_id, who.workspace_account_id)
    if donor.archived:
        raise HTTPException(409, "Архівний автомобіль не можна аналізувати")
    if not donor.ktype:
        return {
            "available": False,
            "reason": "У картці не визначено точну модифікацію (K-Type). Показано локальний план без платного запиту.",
        }
    try:
        rows = client.categories(who.workspace_account_id, int(donor.ktype))
    except PlanPartsError as exc:
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": str(exc.retry_after or 30)} if exc.status == 429 else None) from None
    # Article counts are aftermarket article records, not unique physical parts,
    # and must not be used as the quantity of stock to create.
    total = sum(row.article_count for row in rows)
    return {
        "available": True,
        "categories": len(rows),
        "article_records": total,
        "note": "Артикули різних виробників не дорівнюють кількості окремих деталей автомобіля.",
    }


def _owned_paid_vehicle(who, db, vehicle_id):
    """Only workspace director may spend the provider's tokens during MVP."""
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Платні запити plan.parts доступні лише власнику")
    donor = owned(db, Vehicle, vehicle_id, who.workspace_account_id)
    if donor.archived:
        raise HTTPException(409, "Автомобіль в архіві")
    return donor


def _handle_provider(exc):
    raise HTTPException(exc.status, str(exc),
                        headers={"Retry-After": str(exc.retry_after or 30)} if exc.status == 429 else None) from None


@router.post("/vehicle-matches/lookup")
def vehicle_matches(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
):
    donor = _owned_paid_vehicle(who, db, vehicle_id)
    try:
        rows = client.vehicle_matches(who.workspace_account_id, donor.manufacturer, donor.model, donor.year)
    except PlanPartsError as exc:
        _handle_provider(exc)
    return {"vehicle": f"{donor.manufacturer} {donor.model} {donor.year}",
            "matches": [row.model_dump() for row in rows], "exact_fitment": False,
            "message": "Виберіть модифікацію вручну. Рік та модель не підтверджують сумісність конкретного VIN."}


@router.post("/categories/lookup")
def vehicle_categories(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
):
    donor = _owned_paid_vehicle(who, db, vehicle_id)
    if donor.ktype != ktype:
        raise HTTPException(409, "Спочатку закріпіть вибраний K-Type за автомобілем")
    existing = checklists.stored_categories(db, vehicle_id, who.workspace_account_id, ktype)
    if existing or (donor.checklist_ktype == ktype and donor.checklist_synced_at is not None):
        rows = [CatalogPartType(pt_id=x.pt_id, name=x.name_en, article_count=x.article_count) for x in existing]
        return {"ktype": ktype, "categories": [row.model_dump() for row in rows],
                "category_count": len(rows), "article_records": sum(row.article_count for row in rows),
                "from_saved": True, "message": "Збережений каталог автомобіля, без списання токенів."}
    try:
        rows = client.categories(who.workspace_account_id, ktype)
    except PlanPartsError as exc:
        _handle_provider(exc)
    # Persist a donor-owned potential-parts checklist; never create physical stock.
    checklists.generate(db, vehicle_id, who.workspace_account_id, client, preloaded_rows=rows)
    db.commit()
    return {"ktype": ktype, "categories": [row.model_dump() for row in rows],
            "category_count": len(rows), "article_records": sum(row.article_count for row in rows),
            "from_saved": False, "message": "Це артикули aftermarket, а не фізичні запчастини автомобіля."}


@router.post("/categories/recover")
def recover_vehicle_categories(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
):
    """Cache-only catalogue read. This endpoint cannot spend provider tokens."""
    donor = _owned_paid_vehicle(who, db, vehicle_id)
    if donor.ktype != ktype:
        raise HTTPException(409, "Модифікація автомобіля змінилася")
    stored = checklists.stored_categories(db, vehicle_id, who.workspace_account_id, ktype)
    if stored or (donor.checklist_ktype == ktype and donor.checklist_synced_at is not None):
        rows = [CatalogPartType(pt_id=x.pt_id, name=x.name_en, article_count=x.article_count) for x in stored]
        return {"ktype": ktype, "categories": [row.model_dump() for row in rows],
                "from_saved": True, "category_count": len(rows)}
    try:
        rows = client.recover_categories(who.workspace_account_id, ktype)
    except PlanPartsError as exc:
        _handle_provider(exc)
    return {"ktype": ktype, "categories": [row.model_dump() for row in rows],
            "from_cache": True, "category_count": len(rows)}


@router.post("/articles/recover")
def recover_vehicle_articles(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
    pt_id: int = Query(gt=0),
):
    """Attempt recovery exclusively from previously received in-memory 2xx bytes."""
    donor = _owned_paid_vehicle(who, db, vehicle_id)
    if donor.ktype != ktype:
        raise HTTPException(409, "Модифікація автомобіля змінилася")
    try:
        rows = client.recover_articles(who.workspace_account_id, ktype, pt_id)
    except PlanPartsError as exc:
        _handle_provider(exc)
    return {"ktype": ktype, "pt_id": pt_id, "articles": [row.model_dump() for row in rows],
            "total": len(rows), "from_cache": True}


@router.post("/articles/lookup")
def vehicle_articles(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
    pt_id: int = Query(gt=0),
):
    _owned_paid_vehicle(who, db, vehicle_id)
    try:
        rows = client.articles(who.workspace_account_id, ktype, pt_id)
    except PlanPartsError as exc:
        _handle_provider(exc)
    return {"ktype": ktype, "pt_id": pt_id, "articles": [row.model_dump() for row in rows],
            "total": len(rows), "unique_names": len({row.part_name.casefold() for row in rows if row.part_name}),
            "message": "Кількість різних назв є орієнтиром, не гарантованим переліком деталей для розбору."}


class ChooseKtype(BaseModel):
    ktype: int = Field(strict=True, gt=0, le=2147483647)


@router.post("/vehicle-modification/select")
def select_vehicle_modification(
    data: ChooseKtype,
    who: Annotated[Identity, Depends(identity)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
):
    """Explicit owner selection of provider K-Type scoped to one donor.

    Source is user-selected rather than independently VIN-verified.
    This endpoint cannot spend tokens or modify stock/finance/other donors.
    """
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Вибір модифікації доступний лише власнику")
    donor = owned(db, Vehicle, vehicle_id, who.workspace_account_id, lock=True, active=True)
    if donor.ktype != data.ktype:
        before = snapshot(donor)
        donor.ktype = data.ktype
        record(db, who.workspace_account_id, donor, "vehicle_update",
               "Власник вручну вибрав модифікацію K-Type з plan.parts; сумісність VIN не перевірена", before)
        db.commit()
    return {"vehicle_id": donor.id, "ktype": donor.ktype, "verified_by_vin": False}


class TranslationRequest(BaseModel):
    names: list[str] = Field(min_length=1, max_length=400)


@router.post("/translations/lookup")
def translate_catalogue_names(
    data: TranslationRequest,
    who: Annotated[Identity, Depends(identity)],
):
    """Translate generic part-name strings, not scoped to any car, without plan.parts charges."""
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Машинний переклад каталогу доступний лише власнику")
    try:
        return translate_names(data.names)
    except TranslationError as exc:
        raise HTTPException(exc.code, str(exc)) from None



class AddSelectedDonorPart(BaseModel):
    ktype: int = Field(strict=True, gt=0)
    pt_id: int = Field(strict=True, gt=0)
    ukrainian_name: str = Field(min_length=2, max_length=200)


@router.get("/donor-parts/status")
def donor_part_stock_status(
    who: Annotated[Identity, Depends(identity)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
):
    """Return actual persisted supplier-origin parts and quantities for a donor.

    No paid supplier API calls, and no reliance on a page-local 'added' flag.
    """
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Перегляд інтеграції доступний лише власнику")
    donor = owned(db, Vehicle, vehicle_id, who.workspace_account_id, active=True)
    if donor.ktype != ktype:
        raise HTTPException(409, "Модифікація автомобіля змінилася")
    prefix = f"plan.parts:ktype={ktype};pt_id="
    existing = list(db.scalars(select(Part).where(
        Part.account_id == who.workspace_account_id,
        Part.vehicle_id == donor.id,
        Part.compatibility_notes.like(prefix + "%"),
    ).order_by(Part.created_at)))
    grouped = {}
    for p in existing:
        if p.archived:
            continue
        grouped.setdefault(" ".join(p.name.strip().casefold().split()), []).append(p)
    duplicates = [{"name": rows[0].name, "count": len(rows), "part_ids": [p.id for p in rows]}
                  for rows in grouped.values() if len(rows) > 1]
    return {"parts": [
        {"id": p.id, "pt_id": int(p.compatibility_notes[len(prefix):])
         if p.compatibility_notes[len(prefix):].isdigit() else None,
         "name": p.name, "quantity": p.quantity, "archived": p.archived,
         "article_number": p.article_number}
        for p in existing
    ], "duplicate_names": duplicates}


class ConfirmDonorArticle(BaseModel):
    ktype: int = Field(strict=True, gt=0)
    pt_id: int = Field(strict=True, gt=0)
    art_id: int = Field(strict=True, gt=0)
    part_id: str = Field(min_length=1, max_length=36)


@router.post("/donor-parts/article/select")
def select_donor_part_article(
    data: ConfirmDonorArticle,
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
):
    """Owner-confirmed aftermarket reference for an existing stock card.

    Read ONLY the already-paid provider cache. Never call paid endpoints here.
    Do not assign a supplier offer automatically or claim verified OEM fitment.
    """
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Призначати артикул може лише власник")
    donor = owned(db, Vehicle, vehicle_id, who.workspace_account_id, lock=True, active=True)
    if donor.ktype != data.ktype:
        raise HTTPException(409, "Модифікація автомобіля змінилася")
    part = owned(db, Part, data.part_id, who.workspace_account_id, lock=True, active=True)
    if part.vehicle_id != donor.id or not part.compatibility_notes.startswith(
            f"plan.parts:ktype={data.ktype};pt_id="):
        raise HTTPException(422, "Запчастина не належить цьому донору та каталогу")
    if part.quantity < 1:
        raise HTTPException(409, "Спочатку додайте запчастину на склад")
    try:
        rows = client.recover_articles(who.workspace_account_id, data.ktype, data.pt_id)
    except PlanPartsError as exc:
        _handle_provider(exc)
    offer = next((x for x in rows if x.art_id == data.art_id), None)
    if offer is None:
        raise HTTPException(422, "Артикулу немає в підтвердженій відповіді Plan.Parts")
    if len(offer.article_nr) > 150:
        raise HTTPException(422, "Артикул перевищує ліміт картки складу")
    if part.article_number == offer.article_nr:
        return {"part_id": part.id, "article_number": part.article_number, "changed": False}
    before = snapshot(part)
    part.article_number = offer.article_nr
    record(db, who.workspace_account_id, part, "part_update",
           f"Власник вибрав aftermarket-артикул із Plan.Parts: тип {data.pt_id}, артикул {data.art_id}; VIN/OEM не підтверджено", before)
    db.commit()
    return {"part_id": part.id, "article_number": part.article_number, "changed": True}


@router.post("/donor-parts/add")
def add_selected_donor_part(
    data: AddSelectedDonorPart,
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
):
    """Add exactly one selected donor type to stock with one user action.

    A server-side, cache-only check verifies pt_id membership in the selected
    K-Type catalogue. No paid API calls or reference-catalogue mutations.
    Replays for the same donor/pt_id are idempotent; prevent concurrent inserts
    by serializing on the donor row.
    """
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Додавання з зовнішнього каталогу поки доступне лише власнику")
    donor = owned(db, Vehicle, vehicle_id, who.workspace_account_id, lock=True, active=True)
    if donor.ktype != data.ktype:
        raise HTTPException(409, "Вибрана модифікація автомобіля змінилася")
    stored = checklists.stored_categories(db, vehicle_id, who.workspace_account_id, data.ktype)
    if stored:
        types = [CatalogPartType(pt_id=x.pt_id, name=x.name_en, article_count=x.article_count) for x in stored]
    else:
        try:
            types = client.recover_categories(who.workspace_account_id, data.ktype)
        except PlanPartsError as exc:
            _handle_provider(exc)
    if not any(cat.pt_id == data.pt_id for cat in types):
        raise HTTPException(422, "Вибраного типу немає в перевіреному каталозі цієї модифікації")
    # Classify the *verified* generic supplier type, not a user-submitted
    # category ID. Match only preexisting CarPot categories of this workspace.
    verified_type = next(cat for cat in types if cat.pt_id == data.pt_id)
    classification = match_existing_category(
        db, who.workspace_account_id,
        classify(getattr(verified_type, 'name', ''), data.ukrainian_name), data.ukrainian_name)
    # Reference ID is part of CarPot's internal provenance, not an article copy.
    marker = f"plan.parts:ktype={data.ktype};pt_id={data.pt_id}"
    previous = db.scalar(select(Part).where(
        Part.account_id == who.workspace_account_id,
        Part.vehicle_id == donor.id,
        Part.compatibility_notes == marker,
    ).order_by(Part.created_at))
    if previous is None:
        # A provider can assign several pt_ids to the same named component.
        # On a specific donor, don't create a second stock card for exactly
        # the same normalized Ukrainian name from an earlier plan.parts type.
        # Never merge different donors or manually added parts.
        normalized_name = " ".join(data.ukrainian_name.strip().casefold().split())
        sibling_rows = list(db.scalars(select(Part).where(
            Part.account_id == who.workspace_account_id,
            Part.vehicle_id == donor.id,
            Part.compatibility_notes.like(f"plan.parts:ktype={data.ktype};pt_id=%"),
        ).order_by(Part.created_at)))
        previous = next((
            row for row in sibling_rows
            if " ".join(row.name.strip().casefold().split()) == normalized_name
        ), None)
    if previous is not None:
        if previous.archived:
            raise HTTPException(409, "Запчастина в архіві. Спочатку відновіть її в картці складу")
        if previous.quantity == 0:
            # Previous versions registered the part as a zero-stock candidate.
            # Upgrade exactly once with an audited receipt, not a duplicate.
            stock(db, previous, StockInput(
                type="receipt", quantity=1,
                reason="Оприбутковано вибрану запчастину plan.parts одним натисканням",
            ), who.workspace_account_id)
            db.commit()
            return {"created": False, "received": True, "part_id": previous.id,
                    "name": previous.name, "quantity": previous.quantity,
                    "message": "Раніше додану запчастину оприбутковано: 1 одиниця"}
        return {"created": False, "received": False, "part_id": previous.id,
                "name": previous.name, "quantity": previous.quantity,
                "message": "Запчастина вже на складі; повторного надходження не створено"}
    name = data.ukrainian_name.strip()
    if not any(ch in "іїєґІЇЄҐ" or "\u0400" <= ch <= "\u04ff" for ch in name):
        raise HTTPException(422, "Вкажіть українську назву деталі")
    part = Part(
        account_id=who.workspace_account_id,
        vehicle_id=donor.id,
        name=name,
        category_id=classification["category_id"],
        subcategory_id=classification["subcategory_id"],
        inventory_origin="manual",
        quantity_basis="assumed",
        physical_location_kind="on_vehicle",
        availability="unchecked",
        condition="unknown",
        quantity=0,
        compatibility_notes=marker,
        description="Додано користувачем з довідника типів plan.parts. Точна відповідність VIN та OEM потребує звірки.",
    )
    db.add(part)
    record(db, who.workspace_account_id, part, "part_create",
           "Створено облікову картку вибраної запчастини plan.parts", {})
    # A stock receipt is mandatory in the same transaction so quantity,
    # inventory counters and audit trail remain consistent.
    stock(db, part, StockInput(
        type="receipt", quantity=1,
        reason="Оприбуткування запчастини, вибраної власником для цього донора",
    ), who.workspace_account_id)
    db.commit()
    return {"created": True, "received": True, "part_id": part.id,
            "name": name, "quantity": part.quantity,
            "classification": {k: classification[k] for k in ("kind", "section", "mapping")},
            "message": "Запчастину додано на склад: 1 одиниця"}


@router.post("/donor-parts/receive-pending")
def receive_previously_added_parts(
    who: Annotated[Identity, Depends(identity)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
):
    """One-time audited stock receipt for legacy zero-balance plan.parts selections.

    Only already selected, existing positions for this exact donor/K-Type can be
    received. Other donor parts and manually recorded zero quantities are never
    modified. On repeated calls the response is a harmless no-op.
    """
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Оприбуткування зовнішнього каталогу доступне лише власнику")
    donor = owned(db, Vehicle, vehicle_id, who.workspace_account_id, lock=True, active=True)
    if donor.ktype != ktype:
        raise HTTPException(409, "Вибрана модифікація автомобіля змінилася")
    marker = f"plan.parts:ktype={ktype};pt_id="
    pending = list(db.scalars(select(Part).where(
        Part.account_id == who.workspace_account_id,
        Part.vehicle_id == donor.id,
        Part.archived.is_(False),
        Part.quantity == 0,
        Part.compatibility_notes.like(marker + "%"),
    ).with_for_update()))
    for part in pending:
        stock(db, part, StockInput(
            type="receipt", quantity=1,
            reason="Разове оприбуткування раніше вибраної запчастини plan.parts",
        ), who.workspace_account_id)
    db.commit()
    return {"received_count": len(pending),
            "message": "Раніше додані позиції оприбутковано без повторного створення"}


def _owner_plan_parts_donor(who, db, vehicle_id: str, ktype: int, *, lock=False):
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Класифікація зовнішніх даних доступна лише власнику")
    donor = owned(db, Vehicle, vehicle_id, who.workspace_account_id, lock=lock, active=True)
    if donor.ktype != ktype:
        raise HTTPException(409, "Вибрана модифікація автомобіля змінилася")
    return donor


def _legacy_classification_plan(db, who, donor, ktype):
    """Analyze existing parts, no mutation or external API calls."""
    prefix = f"plan.parts:ktype={ktype};pt_id="
    parts = list(db.scalars(select(Part).where(
        Part.account_id == who.workspace_account_id,
        Part.vehicle_id == donor.id,
        Part.archived.is_(False),
        Part.compatibility_notes.like(prefix + "%"),
    ).order_by(Part.created_at)))
    rows = []
    for part in parts:
        # A historical stock card has only the confirmed saved Ukrainian name;
        # classify conservatively rather than reconstructing a vanished API body.
        proposal = match_existing_category(db, who.workspace_account_id,
                                           classify("", part.name), part.name)
        if part.category_id is not None:
            action = "already_categorized"
        elif proposal["category_id"] is None:
            action = "needs_review"
        else:
            action = "can_apply"
        rows.append({
            "part_id": part.id, "name": part.name,
            "kind": proposal["kind"], "section": proposal["section"],
            "mapping": proposal["mapping"], "action": action,
            "category_id": proposal["category_id"],
            "subcategory_id": proposal["subcategory_id"]
        })
    return rows


@router.get("/donor-parts/classification/preview")
def donor_classification_preview(
    who: Annotated[Identity, Depends(identity)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
):
    donor = _owner_plan_parts_donor(who, db, vehicle_id, ktype)
    rows = _legacy_classification_plan(db, who, donor, ktype)
    return {
        "rows": rows, "total": len(rows),
        "can_apply": sum(r["action"] == "can_apply" for r in rows),
        "needs_review": sum(r["action"] == "needs_review" for r in rows),
        "already_categorized": sum(r["action"] == "already_categorized" for r in rows),
        "no_stock_changes": True,
    }


@router.post("/donor-parts/classification/apply")
def donor_classification_apply(
    who: Annotated[Identity, Depends(identity)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
):
    """Owner-confirmed metadata-only repair of previously uncategorized parts.

    No inserts, deletes, sales, receipts or changes to quantities and prices.
    Existing category choices are never overwritten.
    """
    donor = _owner_plan_parts_donor(who, db, vehicle_id, ktype, lock=True)
    plan = _legacy_classification_plan(db, who, donor, ktype)
    updated = []
    for row in plan:
        if row["action"] != "can_apply":
            continue
        part = owned(db, Part, row["part_id"], who.workspace_account_id, lock=True)
        if part.vehicle_id != donor.id or part.category_id is not None:
            continue
        before = snapshot(part)
        part.category_id = row["category_id"]
        part.subcategory_id = row["subcategory_id"]
        record(db, who.workspace_account_id, part, "part_update",
               "Уточнено категорію запчастини plan.parts без зміни залишків", before)
        updated.append(part.id)
    db.commit()
    return {"updated_count": len(updated), "part_ids": updated,
            "needs_review": sum(r["action"] == "needs_review" for r in plan),
            "message": "Категорії оновлено; складські залишки та ціни не змінено"}

class AddSelectedDonorPartBatch(BaseModel):
    """One explicit user action, at most 40 source types per API request."""
    items: list[AddSelectedDonorPart] = Field(min_length=1, max_length=40)


@router.post("/donor-parts/add-batch")
def add_selected_donor_parts_batch(
    data: AddSelectedDonorPartBatch,
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
):
    """Add selected types using existing audited receipt/idempotency implementation.

    No paid lookup is triggered. Per-item outcomes make interrupted batches
    resumable and prevent invisible partial-success reports.
    """
    if len({item.pt_id for item in data.items}) != len(data.items):
        raise HTTPException(422, "Повторювані типи в одному запиті")
    if len({item.ktype for item in data.items}) != 1:
        raise HTTPException(422, "Типи належать різним модифікаціям автомобіля")
    results = []
    for item in data.items:
        try:
            result = add_selected_donor_part(item, who, client, db, vehicle_id)
            results.append({"pt_id": item.pt_id, "ok": True, **result})
        except HTTPException as exc:
            db.rollback()
            results.append({"pt_id": item.pt_id, "ok": False,
                            "error": str(exc.detail), "status": exc.status_code})
            # If cache/identity/permissions are invalid for one item they are
            # invalid for remaining requests. Avoid unneeded retries.
            if exc.status_code in (401, 403, 409, 429, 502, 503):
                break
        except Exception:
            db.rollback()
            # Unknown commit outcome: abort, never automatically retry.
            results.append({"pt_id": item.pt_id, "ok": False,
                            "error": "Результат запису невідомий. Оновіть статус складу перед повтором."})
            break
    return {"results": results, "completed": sum(bool(r["ok"]) for r in results),
            "attempted": len(results), "requested": len(data.items)}
