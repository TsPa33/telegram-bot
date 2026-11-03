from app.api.secure_route import SecureRoute
"""Paid lookups use POST to require the existing session and CSRF checks."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Vehicle
from app.services.inventory import owned

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
            exc.status, str(exc), headers={"Retry-After": "60"} if exc.status == 429 else None
        ) from None


@router.post("/models/lookup", response_model=list[ModelOption])
def models(who: Annotated[Identity, Depends(identity)],
           client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
           mfa_id: int = Query(gt=0)):
    try:
        return client.models(who.workspace_account_id, mfa_id)
    except PlanPartsError as exc:
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": "60"} if exc.status == 429 else None) from None


@router.post("/modifications/lookup", response_model=list[Modification])
def modifications(who: Annotated[Identity, Depends(identity)],
                  client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
                  ms_id: int = Query(gt=0), year: int | None = Query(default=None, ge=1886, le=2100)):
    try:
        return modifications_for_year(client.modifications(who.workspace_account_id, ms_id), year)
    except PlanPartsError as exc:
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": "60"} if exc.status == 429 else None) from None


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
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": "60"} if exc.status == 429 else None) from None
    # Article counts are aftermarket article records, not unique physical parts,
    # and must not be used as the quantity of stock to create.
    total = sum(row.article_count for row in rows)
    return {
        "available": True,
        "categories": len(rows),
        "article_records": total,
        "note": "Артикули різних виробників не дорівнюють кількості окремих деталей автомобіля.",
    }
