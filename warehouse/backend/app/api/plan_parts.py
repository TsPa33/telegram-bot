from app.api.secure_route import SecureRoute
"""Paid lookups use POST to require the existing session and CSRF checks."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from datetime import datetime, timezone
from uuid import uuid4
from app.models.plan_parts_receipt import PlanPartsArticleReceipt
from app.models import Part
from app.services import checklists
from app.services.plan_parts_classification import classify, match_existing_category
from app.db import get_db
from app.models import Vehicle
from app.services.inventory import owned, record, snapshot, stock
from app.schemas import StockInput
from app.services.parts_translation import translate_names, TranslationError

from app.api.deps import Identity, identity
from app.services.plan_parts import (
    Brand,
    ModelOption,
    Modification,
    CatalogPartType,
    Article,
    PlanPartsClient,
    PlanPartsError,
    modifications_for_year,
)

router = APIRouter(
    route_class=SecureRoute, prefix="/api/v1/plan-parts", tags=["Plan.Parts"]
)


def plan_parts_client(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    who: Annotated[Identity, Depends(identity)],
    request_key: str | None = Query(None, pattern=r"^[a-f0-9-]{36}$"),
    confirm_paid: bool = False,
    max_tokens: int | None = Query(None, ge=0, le=10000),
    force_paid: bool = False,
):
    from app.services.plan_parts_persistence import ResponseStore

    return PlanPartsClient(
        store=ResponseStore(
            db,
            who,
            request.query_params.get("vehicle_id") or request.path_params.get("id"),
            request_key,
            confirm_paid,
            max_tokens,
            force_paid,
        )
    )


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
    confirm_credit: bool = False,
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
    from app.services import billing
    if billing.enabled() and not billing.exempt(who.workspace_account_id) and not confirm_credit:
        raise HTTPException(409,'Підтвердіть використання 1 розбору після успішного збереження каталогу')
    try:
        if billing.enabled() and not billing.exempt(who.workspace_account_id):
            checklists.generate(db,vehicle_id,who.workspace_account_id,client)
            rows=[CatalogPartType(pt_id=x.pt_id,name=x.name_en,article_count=x.article_count) for x in checklists.stored_categories(db,vehicle_id,who.workspace_account_id,ktype)]
        else:
            rows=client.categories(who.workspace_account_id,ktype)
            checklists.generate(db,vehicle_id,who.workspace_account_id,client,preloaded_rows=rows)
    except PlanPartsError as exc:
        _handle_provider(exc)
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
    # Explicit free restoration also persists the previously received list.
    checklists.generate(db,vehicle_id,who.workspace_account_id,client,preloaded_rows=rows,charge=False)
    db.commit()
    return {"ktype": ktype, "categories": [row.model_dump() for row in rows],
            "from_cache": True, "category_count": len(rows)}


def _receipt(db: Session, account_id: str, vehicle_id: str, ktype: int, pt_id: int):
    return db.scalar(select(PlanPartsArticleReceipt).where(
        PlanPartsArticleReceipt.account_id == account_id,
        PlanPartsArticleReceipt.vehicle_id == vehicle_id,
        PlanPartsArticleReceipt.ktype == ktype,
        PlanPartsArticleReceipt.pt_id == pt_id
    ))


def _mark_article_receipt(
    db: Session,
    account_id: str,
    vehicle_id: str,
    ktype: int,
    pt_id: int,
    rows: list[Article],
    *,
    previous=None,
    metadata=None,
):
    now = datetime.now(timezone.utc)
    item = previous or PlanPartsArticleReceipt(
        id=str(uuid4()),
        account_id=account_id,
        vehicle_id=vehicle_id,
        ktype=ktype,
        pt_id=pt_id,
        created_at=now,
    )
    item.status = "received"
    item.article_count = len(rows)
    item.article_snapshot = [row.model_dump(mode="json") for row in rows]
    item.received_at = (
        datetime.fromisoformat(metadata["received_at"])
        if metadata and metadata.get("received_at")
        else item.received_at or now
    )
    if metadata:
        item.response_id = metadata.get("response_id")
        item.response_metadata = metadata
    item.last_checked_at = now
    item.last_error = ""
    db.add(item)
    db.commit()
    return item


def _saved_article_rows(receipt: PlanPartsArticleReceipt | None) -> list[Article] | None:
    """Return an owned immutable-at-read snapshot; empty [] is a valid paid result."""
    if receipt is None or receipt.article_snapshot is None:
        return None
    return [Article.model_validate(row) for row in receipt.article_snapshot]


@router.get("/articles/history")
def article_receipt_history(
    who: Annotated[Identity, Depends(identity)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
):
    """Return durable metadata only; cannot spend provider tokens."""
    donor = _owned_paid_vehicle(who, db, vehicle_id)
    if donor.ktype != ktype:
        raise HTTPException(409, "Модифікація автомобіля змінилася")
    receipts = db.scalars(select(PlanPartsArticleReceipt).where(
        PlanPartsArticleReceipt.account_id == who.workspace_account_id,
        PlanPartsArticleReceipt.vehicle_id == donor.id,
        PlanPartsArticleReceipt.ktype == ktype
    )).all()
    return {"receipts": [{
        "pt_id": x.pt_id,
        "status": x.status,
        "stored": x.article_snapshot is not None,
        "article_count": x.article_count,
        "received_at": x.received_at.isoformat() if x.received_at else None,
        "last_checked_at": x.last_checked_at.isoformat(),
    } for x in receipts]}


@router.post("/articles/recover")
def recover_vehicle_articles(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
    pt_id: int = Query(gt=0),
):
    """Restore a validated stored result first. Never send a paid provider request."""
    donor = _owned_paid_vehicle(who, db, vehicle_id)
    if donor.ktype != ktype:
        raise HTTPException(409, "Модифікація автомобіля змінилася")
    history = _receipt(db, who.workspace_account_id, donor.id, ktype, pt_id)
    persisted = _saved_article_rows(history)
    if persisted is not None:
        return {"ktype": ktype, "pt_id": pt_id, "articles": [r.model_dump(mode="json") for r in persisted],
                "total": len(persisted), "from_saved": True, "previously_received": True}
    try:
        rows = client.recover_articles(who.workspace_account_id, ktype, pt_id)
    except PlanPartsError as exc:
        if history and exc.status == 409:
            history.status = "unavailable" if history.received_at else "uncertain"
            history.last_checked_at = datetime.now(timezone.utc)
            db.commit()
            raise HTTPException(409, {
                "code": "previously_received_unavailable" if history.received_at else "previous_payment_uncertain",
                "message": "Отримано раніше — дані потребують відновлення. Новий платний запит не виконувався." if history.received_at else "Попередній запит має невизначений результат; платний повтор заблоковано.",
                "article_count": history.article_count,
                "received_at": history.received_at.isoformat() if history.received_at else None
            }) from None
        _handle_provider(exc)
    _mark_article_receipt(db, who.workspace_account_id, donor.id, ktype, pt_id, rows, previous=history, metadata=getattr(client,"last_metadata",{}))
    return {"ktype": ktype, "pt_id": pt_id, "articles": [row.model_dump(mode="json") for row in rows],
            "total": len(rows), "from_cache": True, "from_saved": False, "previously_received": True}


@router.post("/articles/lookup")
def vehicle_articles(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
    ktype: int = Query(gt=0),
    pt_id: int = Query(gt=0),
    force_paid: bool = Query(default=False),
):
    donor = _owned_paid_vehicle(who, db, vehicle_id)
    if donor.ktype != ktype:
        raise HTTPException(409, "Модифікація автомобіля змінилася")
    history = _receipt(db, who.workspace_account_id, donor.id, ktype, pt_id)
    persisted = _saved_article_rows(history)
    recovered_without_payment = False
    if persisted is not None and not force_paid:
        rows = persisted
        recovered_without_payment = True
    elif history and not force_paid:
        try:
            rows = client.recover_articles(who.workspace_account_id, ktype, pt_id)
        except PlanPartsError as exc:
            if exc.status == 409:
                history.status = "unavailable" if history.received_at else "uncertain"
                history.last_checked_at = datetime.now(timezone.utc)
                db.commit()
                raise HTTPException(409, {
                    "code": "previously_received_unavailable" if history.received_at else "previous_payment_uncertain",
                    "message": "Отримано раніше — дані потребують відновлення. Повторну оплату заблоковано." if history.received_at else "Попередня оплата не підтверджена; повторний платний запит заблоковано.",
                    "article_count": history.article_count
                }) from None
            _handle_provider(exc)
        _mark_article_receipt(db, who.workspace_account_id, donor.id, ktype, pt_id, rows, previous=history, metadata=getattr(client,"last_metadata",{}))
        recovered_without_payment = True
    else:
        if history is None:
            now = datetime.now(timezone.utc)
            history = PlanPartsArticleReceipt(
                id=str(uuid4()), account_id=who.workspace_account_id,
                vehicle_id=donor.id, ktype=ktype, pt_id=pt_id,
                status="uncertain", article_count=0, created_at=now,
                last_checked_at=now, last_error=""
            )
            db.add(history)
            try:db.commit()  # Write-ahead evidence before any chargeable request.
            except IntegrityError:
                db.rollback()
                raise HTTPException(409,'Запит цього типу вже розпочато; перечитайте збережений стан') from None
        else:
            history.status = "uncertain"
            history.last_checked_at = datetime.now(timezone.utc)
            db.commit()
        try:
            rows = client.articles(who.workspace_account_id, ktype, pt_id)
        except PlanPartsError as exc:
            definite=exc.status==429 or exc.status in (403,428,503) and getattr(getattr(client,'store',None),'current',None) is None
            if definite:
                if history.received_at:
                    history.status = "received" if history.article_snapshot is not None else "unavailable"
                else:
                    db.delete(history)
                db.commit()
            else:
                history.last_error = "Невизначений результат запиту; перевірте безкоштовне відновлення"
                history.last_checked_at = datetime.now(timezone.utc)
                db.commit()
            _handle_provider(exc)
        _mark_article_receipt(db, who.workspace_account_id, donor.id, ktype, pt_id, rows, previous=history, metadata=getattr(client,"last_metadata",{}))
    return {"ktype": ktype, "pt_id": pt_id, "articles": [row.model_dump(mode="json") for row in rows],
            "total": len(rows), "unique_names": len({row.part_name.casefold() for row in rows if row.part_name}),
            "from_cache": recovered_without_payment, "from_saved": persisted is not None and not force_paid,"metadata":getattr(client,"last_metadata",{}) or (history.response_metadata if history else {}) or {},
            "message": "Aftermarket-пропозиції; сумісність фізичної запчастини потрібно перевірити."}


class ChooseKtype(BaseModel):
    confirm_change: bool = False
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
        from app.models import PlanPartsResponse, VehicleChecklistItem
        has_previous = db.scalar(select(VehicleChecklistItem.id).where(VehicleChecklistItem.account_id == who.workspace_account_id, VehicleChecklistItem.vehicle_id == donor.id).limit(1))
        if donor.ktype and has_previous and not data.confirm_change:
            raise HTTPException(409, "Зміна модифікації відкриє окремий список. Попередні деталі та артикули збережені. Підтвердьте зміну.")
        before = snapshot(donor)
        donor.ktype = data.ktype
        saved = db.scalars(select(PlanPartsResponse).where(PlanPartsResponse.account_id == who.workspace_account_id, PlanPartsResponse.resource == "ktype", PlanPartsResponse.status == "validated").order_by(PlanPartsResponse.created_at.desc()))
        for response in saved:
            selected = next((r for r in (response.normalized or []) if str(r.get("ktype")) == str(data.ktype)), None)
            if selected and selected.get("modification"):
                donor.engine = str(selected["modification"])[:100]
                break
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
         "article_number": p.article_number, "article_brand": p.article_brand,"oem_number":p.oem_number,"article_provenance":p.article_provenance,"oem_provenance":p.oem_provenance}
        for p in existing
    ], "duplicate_names": duplicates}


class ConfirmDonorArticle(BaseModel):
    ktype: int = Field(strict=True, gt=0)
    pt_id: int = Field(strict=True, gt=0)
    art_id: int = Field(strict=True, gt=0)
    part_id: str = Field(min_length=1, max_length=36)
    expected_article_number: str | None = Field(default=None,max_length=150)
    expected_article_brand: str | None = Field(default=None,max_length=200)


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
    if part.vehicle_id != donor.id or part.compatibility_notes != f"plan.parts:ktype={data.ktype};pt_id={data.pt_id}":
        raise HTTPException(422, "Запчастина не належить цьому донору та каталогу")
    if part.quantity < 1:
        raise HTTPException(409, "Спочатку додайте запчастину на склад")
    saved = _receipt(db, who.workspace_account_id, donor.id, data.ktype, data.pt_id)
    rows = _saved_article_rows(saved)
    if rows is None:
        try:
            rows = client.recover_articles(
                who.workspace_account_id, data.ktype, data.pt_id
            )
        except PlanPartsError as exc:
            _handle_provider(exc)
        saved = _mark_article_receipt(
            db,
            who.workspace_account_id,
            donor.id,
            data.ktype,
            data.pt_id,
            rows,
            previous=saved,
            metadata=getattr(client, "last_metadata", {}),
        )
    # Recovery may commit a durable response. Reacquire and revalidate before assignment.
    donor = owned(
        db, Vehicle, vehicle_id, who.workspace_account_id, lock=True, active=True
    )
    part = owned(
        db, Part, data.part_id, who.workspace_account_id, lock=True, active=True
    )
    db.refresh(donor)
    db.refresh(part)
    if (
        donor.archived
        or part.archived
        or donor.ktype != data.ktype
        or part.vehicle_id != donor.id
        or part.compatibility_notes
        != f"plan.parts:ktype={data.ktype};pt_id={data.pt_id}"
        or part.quantity < 1
    ):
        raise HTTPException(
            409, "Автомобіль або складська позиція змінилися; перечитайте дані"
        )
    offer = next((x for x in rows if x.art_id == data.art_id), None)
    if offer is None:
        raise HTTPException(422, "Артикулу немає в підтвердженій відповіді Plan.Parts")
    if len(offer.article_nr) > 150:
        raise HTTPException(422, "Артикул перевищує ліміт картки складу")
    if (
        data.expected_article_number is not None
        and (
            part.article_number != data.expected_article_number
            or data.expected_article_brand is not None
            and part.article_brand != data.expected_article_brand
        )
        and (
            part.article_number != offer.article_nr or part.article_brand != offer.brand
        )
    ):
        raise HTTPException(
            409, "Артикул уже змінено. Перечитайте позицію перед підтвердженням."
        )
    if part.article_number == offer.article_nr and part.article_brand == offer.brand:
        return {
            "part_id": part.id,
            "article_number": part.article_number,
            "article_brand": part.article_brand,
            "changed": False,
        }
    before = snapshot(part)
    part.article_number = offer.article_nr
    part.article_brand = offer.brand
    part.article_provenance = dict(
        source="plan.parts",
        art_id=data.art_id,
        ktype=data.ktype,
        pt_id=data.pt_id,
        vehicle_id=donor.id,
        confirmed_by=who.actor_id,
        response_id=getattr(client, "last_metadata", {}).get("response_id")
        or getattr(saved, "response_id", None),
        receipt_id=getattr(saved, "id", None),
        fitment_confirmed=False,
    )
    record(
        db,
        who.workspace_account_id,
        part,
        "part_update",
        f"Власник вибрав aftermarket-артикул із Plan.Parts: тип {data.pt_id}, артикул {data.art_id}; VIN/OEM не підтверджено",
        before,
    )
    db.commit()
    return {
        "part_id": part.id,
        "article_number": part.article_number,
        "article_brand": part.article_brand,
        "changed": True,
    }


@router.post("/donor-parts/add")
def add_selected_donor_part(
    data: AddSelectedDonorPart,
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
):
    result = add_selected_donor_parts_batch(AddSelectedDonorPartBatch(items=[data]), who, client, db, vehicle_id)
    return result['results'][0]


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
    from app.models import Operation
    marker = f"plan.parts:ktype={ktype};pt_id="
    pending = list(db.scalars(select(Part).where(
        Part.account_id == who.workspace_account_id,
        Part.vehicle_id == donor.id,
        Part.archived.is_(False),
        Part.quantity == 0,
        ~select(Operation.id).where(Operation.account_id==who.workspace_account_id,Operation.part_id==Part.id,Operation.type.in_(['receipt','sale','write_off'])).exists(),
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


class CategoryRepair(BaseModel):
    token: str = Field(min_length=64,max_length=64)
    provision: bool = False


@router.get("/donor-parts/classification/preview")
def donor_classification_preview(who: Annotated[Identity,Depends(identity)],db:Annotated[Session,Depends(get_db)],vehicle_id:str=Query(min_length=1,max_length=80),ktype:int=Query(gt=0),provision:bool=False):
    from app.services.source_types import normalization
    from app.services.entitlements import require_paid
    if provision:require_paid(db,who.workspace_account_id)
    donor=_owner_plan_parts_donor(who,db,vehicle_id,ktype)
    return normalization(db,who,donor,provision=provision)


@router.post("/donor-parts/classification/apply")
def donor_classification_apply(data:CategoryRepair,who:Annotated[Identity,Depends(identity)],db:Annotated[Session,Depends(get_db)],vehicle_id:str=Query(min_length=1,max_length=80),ktype:int=Query(gt=0)):
    from app.models import Account
    from app.services.source_types import normalization
    db.scalar(select(Account).where(Account.id==who.workspace_account_id).with_for_update())
    donor=_owner_plan_parts_donor(who,db,vehicle_id,ktype,lock=True)
    return normalization(db,who,donor,apply=True,token=data.token,provision=data.provision)


class AddSelectedDonorPartBatch(BaseModel):
    """One explicit atomic user action, at most 1000 source types per request."""
    items: list[AddSelectedDonorPart] = Field(min_length=1, max_length=1000)


@router.post("/donor-parts/add-batch")
def add_selected_donor_parts_batch(
    data: AddSelectedDonorPartBatch,
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
    db: Annotated[Session, Depends(get_db)],
    vehicle_id: str = Query(min_length=1, max_length=80),
):
    from app.models import Account
    from app.services.donor_stock_batch import add
    if who.user.role != "DIRECTOR" or who.user.id != who.workspace_account_id:
        raise HTTPException(403, "Додавання доступне лише власнику")
    # Global mapping writers serialize before donor/part locks, across API replicas.
    db.scalar(select(Account).where(Account.id==who.workspace_account_id).with_for_update())
    donor=owned(db,Vehicle,vehicle_id,who.workspace_account_id,lock=True,active=True)
    if donor.ktype is None or any(item.ktype != donor.ktype for item in data.items):
        raise HTTPException(409,'Спочатку виберіть правильну модифікацію автомобіля')
    try:
        return add(db,who,donor,data.items,client)
    except PlanPartsError as exc:
        db.rollback();_handle_provider(exc)
    except Exception:
        db.rollback();raise


@router.get('/workspace')
def saved_workspace(who: Annotated[Identity,Depends(identity)],db:Annotated[Session,Depends(get_db)],vehicle_id:str=Query(min_length=1,max_length=80)):
    """One donor read model; no external calls, cache writes, normalization or stock mutation."""
    from sqlalchemy import func, case
    from sqlalchemy.orm import defer
    from app.models import PlanPartsResponse, VehicleChecklistItem
    from app.services.plan_parts_persistence import policy

    donor = _owned_paid_vehicle(who, db, vehicle_id)
    categories = (
        checklists.stored_categories(
            db, donor.id, who.workspace_account_id, donor.ktype
        )
        if donor.ktype
        else []
    )
    receipts = list(
        db.execute(
            select(
                PlanPartsArticleReceipt.pt_id,
                PlanPartsArticleReceipt.status,
                PlanPartsArticleReceipt.article_count,
                case(
                    (
                        func.json_typeof(PlanPartsArticleReceipt.article_snapshot)
                        == "array",
                        func.json_array_length(
                            PlanPartsArticleReceipt.article_snapshot
                        ),
                    ),
                    else_=0,
                ).label("saved_count"),
                PlanPartsArticleReceipt.received_at,
                PlanPartsArticleReceipt.response_metadata,
                (
                    func.json_typeof(PlanPartsArticleReceipt.article_snapshot)
                    == "array"
                ).label("stored"),
            ).where(
                PlanPartsArticleReceipt.account_id == who.workspace_account_id,
                PlanPartsArticleReceipt.vehicle_id == donor.id,
                PlanPartsArticleReceipt.ktype == donor.ktype,
            )
        ).mappings()
    )
    parts = list(
        db.scalars(
            select(Part).where(
                Part.account_id == who.workspace_account_id,
                Part.vehicle_id == donor.id,
                Part.archived.is_(False),
            )
        )
    )
    prefix = f"plan.parts:ktype={donor.ktype};pt_id="
    pparts = [
        p
        for p in parts
        if p.compatibility_notes.startswith(prefix)
        and p.compatibility_notes[len(prefix) :].isdigit()
    ]
    responses = list(
        db.execute(
            select(
                PlanPartsResponse.id,
                PlanPartsResponse.resource,
                PlanPartsResponse.status,
                PlanPartsResponse.metadata_json,
                PlanPartsResponse.received_at,
                PlanPartsResponse.estimated_max_tokens,
            )
            .where(
                PlanPartsResponse.account_id == who.workspace_account_id,
                PlanPartsResponse.vehicle_id == donor.id,
            )
            .order_by(PlanPartsResponse.created_at.desc())
            .limit(30)
        ).mappings()
    )
    recovery_types = {
        r["pt_id"]
        for r in receipts
        if not r["stored"]
        and (r["received_at"] or r["status"] in ("unavailable", "uncertain"))
    }
    latest_responses = (
        select(PlanPartsResponse.parameters, PlanPartsResponse.status)
        .where(
            PlanPartsResponse.account_id == who.workspace_account_id,
            PlanPartsResponse.resource == "articles",
            PlanPartsResponse.parameters["ktype"].as_integer() == donor.ktype,
        )
        .distinct(PlanPartsResponse.context_hash)
        .order_by(
            PlanPartsResponse.context_hash,
            PlanPartsResponse.created_at.desc(),
            PlanPartsResponse.id.desc(),
        )
        .subquery()
    )
    recovery_types.update(
        db.scalars(
            select(latest_responses.c.parameters["pt_id"].as_integer()).where(
                latest_responses.c.status.in_(
                    ["pending", "uncertain", "invalid", "received"]
                ),
                latest_responses.c.parameters["pt_id"].as_integer().is_not(None),
            )
        )
    )
    from app.services.source_types import Resolver
    resolver=Resolver(db,who.workspace_account_id)
    return dict(
        vehicle_id=donor.id,
        ktype=donor.ktype,
        categories=[
            dict(
                checklist_id=c.id,
                pt_id=c.pt_id,
                name=c.name_en,
                name_uk=c.name_uk,
                article_count=c.article_count,
                classification=resolver.resolve(c.pt_id,c.name_en,c.name_uk or ""),
            )
            for c in categories
        ],
        receipts=[dict(r) for r in receipts],
        parts=[
            dict(
                id=p.id,
                pt_id=int(p.compatibility_notes[len(prefix) :]),
                name=p.name,
                quantity=p.quantity,
                article_number=p.article_number,
                article_brand=p.article_brand,
                oem_number=p.oem_number,
                article_provenance=p.article_provenance,
                oem_provenance=p.oem_provenance,
            )
            for p in pparts
        ],
        saved_plan_ktypes=list(db.scalars(select(VehicleChecklistItem.ktype).where(VehicleChecklistItem.account_id==who.workspace_account_id,VehicleChecklistItem.vehicle_id==donor.id).distinct())),
        saved_modifications=db.scalar(select(PlanPartsResponse.normalized).where(
            PlanPartsResponse.account_id==who.workspace_account_id,PlanPartsResponse.resource=='ktype',PlanPartsResponse.status=='validated',
            PlanPartsResponse.parameters['brand'].as_string()==donor.manufacturer,
            PlanPartsResponse.parameters['model'].as_string()==donor.model,
            PlanPartsResponse.parameters['year'].as_integer()==donor.year,
        ).order_by(PlanPartsResponse.created_at.desc()).limit(1)) or [],
        responses=[dict(r) for r in responses],
        policy=policy(),
        summary=dict(
            types=len(categories),
            saved_variants=sum(r["saved_count"] for r in receipts if r["stored"]),
            article_assigned=sum(bool((p.article_number or "").strip()) for p in parts),
            needs_recovery=len(recovery_types),
            saved_types=sum(bool(r["stored"]) for r in receipts),
            legacy_unavailable=sum(
                bool(r["received_at"]) and not r["stored"] for r in receipts
            ),
            uncertain=sum(r["status"] == "uncertain" for r in receipts),
            stock_positions=len(pparts),
            oem_assigned=sum(bool((p.oem_number or "").strip()) for p in parts),
        ),
    )


@router.get("/responses/{id}")
def response_artifact(
    id: str,
    who: Annotated[Identity, Depends(identity)],
    db: Annotated[Session, Depends(get_db)],
):
    import hashlib
    from fastapi.responses import Response
    from app.models import PlanPartsResponse

    if who.user.role != "DIRECTOR" or who.actor_id != who.workspace_account_id:
        raise HTTPException(403, "Збережені відповіді доступні лише власнику")
    r = db.scalar(
        select(PlanPartsResponse).where(
            PlanPartsResponse.id == id,
            PlanPartsResponse.account_id == who.workspace_account_id,
        )
    )
    if not r or r.body is None:
        raise HTTPException(404, "Збереженої відповіді немає")
    if hashlib.sha256(r.body).hexdigest() != r.sha256:
        raise HTTPException(409, "Контрольна сума не збігається")
    return Response(
        r.body,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="plan-parts-response.json"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Content-SHA256": r.sha256,
        },
    )
