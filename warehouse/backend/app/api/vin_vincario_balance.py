"""Explicit, platform-admin-only Vincario balance probe, with no VIN decoding."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import identity, Identity
from app.api.secure_route import SecureRoute
from app.db import get_db
from app.services.catalogue_import import platform_admin
from app.services.vin_vincario_balance import configured, fetch_balance

router = APIRouter(prefix="/api/v1/vehicles/vin/vincario",
                   route_class=SecureRoute, tags=["Vincario balance only"])
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


@router.get("/readiness")
def readiness(db: DB, who: Auth):
    if not platform_admin(who.user):
        raise HTTPException(403, "Доступно лише адміністратору платформи")
    return {"credentials_configured": configured(),
            "decode_enabled": False, "billing_enabled": False,
            "balance_check_available": configured()}


@router.post("/balance")
def balance(db: DB, who: Auth):
    if not platform_admin(who.user):
        raise HTTPException(403, "Доступно лише адміністратору платформи")
    return fetch_balance()
