from typing import Annotated, Literal
from pydantic import Field, model_validator
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.secure_route import SecureRoute
from app.api.deps import identity, Identity
from app.db import get_db
from app.models import Vehicle
from app.schemas import Input
from app.services.inventory import owned
from app.services import dismantling_workspace as service
from app.permissions import require_permission

router = APIRouter(route_class=SecureRoute, prefix="/api/v1/vehicles")
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


class Keys(Input):
    source: Literal["base", "professional", "catalogue"]
    keys: list[str] = Field(min_length=1, max_length=40)


class Change(Keys):
    keys: list[str] = Field(min_length=1, max_length=1000)
    action: Literal["hide", "restore", "dismantled", "rename"]
    name: str | None = Field(None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid(self):
        if self.action == "rename" and (
            len(self.keys) != 1 or not self.name or not service.is_uk(self.name)
        ):
            raise ValueError("Вкажіть українську назву однієї позиції")
        return self


@router.get("/{id}/dismantling-workspace")
def read(id: str, db: DB, who: Auth, source: Literal["base", "professional", "catalogue"] = "base"):
    require_permission(who, "vehicles.view", "inventory.view", "catalog.view")
    return service.read(
        db, who, owned(db, Vehicle, id, who.workspace_account_id), source
    )


@router.post("/{id}/dismantling-workspace/annotations")
def annotate(id: str, data: Change, db: DB, who: Auth):
    require_permission(who, "vehicles.view", "dismantling.manage")
    v = owned(db, Vehicle, id, who.workspace_account_id, lock=True, active=True)
    service.annotate(db, who, v, data.source, data.keys, data.action, data.name)
    return service.read(db, who, v, data.source)


@router.post("/{id}/dismantling-workspace/translations")
def translate(id: str, data: Keys, db: DB, who: Auth):
    if who.user.role != "DIRECTOR" or who.actor_id != who.workspace_account_id:
        raise HTTPException(403, "Автоматичний переклад доступний власнику")
    return service.translate_batch(
        db,
        who,
        owned(db, Vehicle, id, who.workspace_account_id, active=True),
        data.source,
        data.keys,
    )
