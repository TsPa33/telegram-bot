"""Admin-only preflight for TecAlliance VIN. Never makes an external request."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import identity, Identity
from app.api.secure_route import SecureRoute
from app.db import get_db
from app.services.catalogue_import import platform_admin
from app.services.vin_tecalliance import readiness

router = APIRouter(prefix="/api/v1/vehicles/vin/tecalliance",
                   route_class=SecureRoute, tags=["TecAlliance offline preflight"])
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


@router.get("/readiness")
def tecalliance_readiness(db: DB, who: Auth):
    if not platform_admin(who.user):
        raise HTTPException(403, "Доступно лише адміністратору платформи")
    return readiness()
