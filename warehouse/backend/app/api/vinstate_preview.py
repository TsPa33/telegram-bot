"""Manual VINState smoke-test route. Disabled unless staging explicitly opts in.

This is NOT connected to the paid 50 UAH workflow, nor to automatic decoding.
Only a platform admin can call it, with a valid session and CSRF token.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.api.deps import identity, Identity
from app.api.secure_route import SecureRoute
from app.db import get_db
from app.services.catalogue_import import platform_admin
from app.services import vin_vinstate

router = APIRouter(prefix="/api/v1/vehicles/vin/vinstate", route_class=SecureRoute,
                   tags=["VINState manual diagnostic"])
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vin: str = Field(min_length=17, max_length=17)
    acknowledge_provider_quota: bool = Field(strict=True)


@router.get("/readiness")
def readiness(db: DB, who: Auth):
    if not platform_admin(who.user):
        raise HTTPException(403, "Доступно лише адміністратору платформи")
    return {
        "key_present": bool(__import__("os").getenv("WAREHOUSE_VINSTATE_API_KEY", "").strip()),
        "diagnostic_enabled": vin_vinstate.test_gate_enabled(),
        "free_only_guaranteed": False,
        "billing_connected": False,
        "automatic_lookup_enabled": False,
        "note": "Виклики можуть витрачати VINState-кредити після вичерпання безкоштовної квоти.",
    }


@router.post("/preview")
def preview(body: PreviewInput, db: DB, who: Auth):
    if not platform_admin(who.user):
        raise HTTPException(403, "Доступно лише адміністратору платформи")
    if not body.acknowledge_provider_quota:
        raise HTTPException(422, "Підтвердіть можливе списання квоти провайдера")
    if not vin_vinstate.test_gate_enabled():
        raise HTTPException(503, "Тест VINState вимкнено. API-запит не здійснено.")
    try:
        return vin_vinstate.decode(body.vin)
    except ValueError:
        raise HTTPException(422, "Некоректний VIN") from None
