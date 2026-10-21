"""Paid lookups use POST to require the existing session and CSRF checks."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import Identity, identity
from app.services.plan_parts import Brand, ModelOption, Modification, PlanPartsClient, PlanPartsError, modifications_for_year

router = APIRouter(prefix="/api/v1/plan-parts", tags=["Plan.Parts"])


def plan_parts_client():
    return PlanPartsClient()


@router.post("/brands/lookup", response_model=list[Brand])
def brands(
    who: Annotated[Identity, Depends(identity)],
    client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
):
    try:
        return client.brands(who.user.id)
    except PlanPartsError as exc:
        raise HTTPException(
            exc.status, str(exc), headers={"Retry-After": "60"} if exc.status == 429 else None
        ) from None


@router.post("/models/lookup", response_model=list[ModelOption])
def models(who: Annotated[Identity, Depends(identity)],
           client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
           mfa_id: int = Query(gt=0)):
    try:
        return client.models(who.user.id, mfa_id)
    except PlanPartsError as exc:
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": "60"} if exc.status == 429 else None) from None


@router.post("/modifications/lookup", response_model=list[Modification])
def modifications(who: Annotated[Identity, Depends(identity)],
                  client: Annotated[PlanPartsClient, Depends(plan_parts_client)],
                  ms_id: int = Query(gt=0), year: int | None = Query(default=None, ge=1886, le=2100)):
    try:
        return modifications_for_year(client.modifications(who.user.id, ms_id), year)
    except PlanPartsError as exc:
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": "60"} if exc.status == 429 else None) from None
