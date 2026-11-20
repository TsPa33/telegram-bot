"""Platform owner-only OEM coverage diagnostics, read-only and no API cost."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import Identity,identity
from app.api.secure_route import SecureRoute
from app.db import get_db
from app.services.catalogue_import import platform_admin
from app.services.oem_diagnostics import audit, workspace_stock_audit

router=APIRouter(prefix="/api/v1/oem",route_class=SecureRoute,tags=["OEM coverage audit"])
DB=Annotated[Session,Depends(get_db)]
Auth=Annotated[Identity,Depends(identity)]


@router.get("/admin/coverage")
def coverage(db:DB,who:Auth,workspace_stock:bool=False,vehicle_id:str|None=None):
    if not platform_admin(who.user):
        raise HTTPException(403,"Доступ лише адміністратору платформи")
    if workspace_stock:
        return workspace_stock_audit(db,who.workspace_account_id,vehicle_id)
    return audit(db)
