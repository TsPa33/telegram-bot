"""Explicitly disabled paid VIN offer, quote and confirmation contract.

No external paid VIN API calls. No wallet reservations or charges. Once the
central Billing reserve/capture/release transport is independently approved,
a new reviewed implementation can replace the hard safety gate.
"""
from typing import Annotated
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.api.deps import identity, Identity
from app.api.secure_route import SecureRoute
from app.db import get_db
from app.services.vin_paid_contract import quote, validate_request_key, require_paid_vin_ready

router = APIRouter(prefix="/api/v1/vehicles/vin/paid", route_class=SecureRoute, tags=["Paid VIN preparation"])
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


class ConfirmVIN(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vin: str = Field(min_length=17, max_length=17)
    request_key: str = Field(min_length=16, max_length=80)
    expected_amount_minor: int = Field(strict=True)
    currency: str = Field(min_length=3, max_length=3)
    confirmed: bool = Field(strict=True)


@router.get("/quote")
def paid_quote(vin: str, db: DB, who: Auth):
    # The authenticated account always belongs to the current workspace.
    return quote(vin)


@router.post("/confirm")
def confirm(data: ConfirmVIN, db: DB, who: Auth):
    from fastapi import HTTPException
    offered = quote(data.vin)
    validate_request_key(data.request_key)
    if not data.confirmed:
        raise HTTPException(422, "Підтвердіть вартість запиту")
    if (data.expected_amount_minor, data.currency) != (offered["amount_minor"], offered["currency"]):
        raise HTTPException(409, "Вартість змінилася. Оновіть пропозицію.")
    # Never store a financial intent or simulate a reserve. Financial authority
    # is the central Billing service, not the Warehouse.
    require_paid_vin_ready()
