from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.secure_route import SecureRoute
from app.api.deps import Identity, identity
from app.db import get_db
from app.models import Vehicle
from app.services.inventory import owned
from app.services.aleto_catalog import catalogue

router = APIRouter(route_class=SecureRoute, tags=['Aleto reference'])


@router.get('/api/v1/vehicles/{id}/aleto-catalog')
def vehicle_catalog(id: str, db: Annotated[Session, Depends(get_db)], who: Annotated[Identity, Depends(identity)],
                    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                    category_id: str | None = Query(None, max_length=36),
                    subcategory_id: str | None = Query(None, max_length=36), q: str = Query('', max_length=200)):
    vehicle = owned(db, Vehicle, id, who.workspace_account_id)
    return catalogue(db, vehicle, who.workspace_account_id, offset=offset, limit=limit,
                     category_id=category_id, subcategory_id=subcategory_id, q=q)
