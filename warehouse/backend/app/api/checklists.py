from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from app.api.deps import Identity, identity
from app.api.plan_parts import plan_parts_client
from app.db import get_db
from app.schemas import Input
from app.services.plan_parts import PlanPartsClient, PlanPartsError
from app.services import checklists

router = APIRouter(prefix="/api/v1/vehicles", tags=["Vehicle checklists"])
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


class ChecklistUpdate(Input):
    status: Literal["unchecked", "present", "absent", "damaged"] = "unchecked"
    name_uk: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("Вкажіть зміни")
        return self


@router.get("/{id}/plan-parts-checklist")
def get_checklist(id: str, db: DB, who: Auth, offset: int = Query(0, ge=0),
                  limit: int = Query(100, ge=1, le=200), include_history: bool = False):
    return checklists.listing(db, id, who.user.id, offset=offset, limit=limit, include_history=include_history)


@router.post("/{id}/plan-parts-checklist")
def generate_checklist(id: str, db: DB, who: Auth,
                       client: Annotated[PlanPartsClient, Depends(plan_parts_client)], refresh: bool = False):
    try:
        result = checklists.generate(db, id, who.user.id, client, refresh=refresh)
    except PlanPartsError as exc:
        raise HTTPException(exc.status, str(exc), headers={"Retry-After": "60"} if exc.status == 429 else None) from None
    db.commit()
    return result


@router.patch("/{id}/plan-parts-checklist/{item_id}")
def update_checklist(id: str, item_id: str, data: ChecklistUpdate, db: DB, who: Auth):
    result = checklists.update(db, id, item_id, who.user.id, data.model_dump(exclude_unset=True))
    db.commit()
    return result
