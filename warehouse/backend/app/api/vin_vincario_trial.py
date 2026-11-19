"""Admin-only explicit Vincario Free Demo preview for three known VINs."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import Identity, identity
from app.api.secure_route import SecureRoute
from app.db import get_db
from app.services.catalogue_import import platform_admin
from app.services import vin_vincario_trial

router = APIRouter(prefix="/api/v1/vehicles/vin/vincario",
                   route_class=SecureRoute, tags=["Vincario free demo"])
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


class VINTrialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vin: str = Field(min_length=17, max_length=17)
    acknowledge_free_quota: bool


@router.get("/trial/readiness")
def readiness(db: DB, who: Auth):
    if not platform_admin(who.user):
        raise HTTPException(403, "Доступ лише адміністратору")
    return vin_vincario_trial.readiness()


@router.post("/trial/preview")
def preview(body: VINTrialRequest, db: DB, who: Auth):
    if not platform_admin(who.user):
        raise HTTPException(403, "Доступ лише адміністратору")
    if not body.acknowledge_free_quota:
        raise HTTPException(422, "Підтвердіть використання безкоштовної квоти")
    return vin_vincario_trial.preview(body.vin, acknowledged=True)
