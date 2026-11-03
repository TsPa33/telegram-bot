from app.api.secure_route import SecureRoute
"""Paid lookups use POST to require the existing session and CSRF checks."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Vehicle
from app.services.inventory import owned, record, snapshot

from app.api.deps import Identity, identity
from app.services.plan_parts import Brand, ModelOption, Modification, PlanPartsClient, PlanPartsError, modifications_for_year

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
    _owned_paid_vehicle(who, db, vehicle_id)
    try:
        rows = client.categories(who.workspace_account_id, ktype)
    except PlanPartsError as exc:
        _handle_provider(exc)
    return {"ktype": ktype, "categories": [row.model_dump() for row in rows],
            "category_count": len(rows), "article_records": sum(row.article_count for row in rows),
            "message": "Це артикули aftermarket, а не фізичні запчастини автомобіля."}


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
            "total": len(rows), "unique_names": len({row.part_name.casefold() for row in rows}),
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
