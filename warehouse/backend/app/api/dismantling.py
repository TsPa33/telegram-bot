from typing import Annotated, Literal
from fastapi import APIRouter, Depends
from pydantic import Field, field_validator
from sqlalchemy.orm import Session
from app.api.deps import Identity, identity
from app.db import get_db
from app.schemas import Input, Money
from app.services import dismantling

router = APIRouter(tags=['Dismantling'])
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


class DismantlingAction(Input):
    ids: Annotated[list[str], Field(min_length=1, max_length=100)]
    action: Literal['dismantled', 'absent', 'damaged', 'unchecked', 'receipt']
    quantity: Annotated[int, Field(strict=True, ge=1, le=1000000)] = 1
    condition: Literal['used', 'new', 'damaged', 'refurbished'] | None = None
    location: Annotated[str, Field(max_length=120)] = ''
    selling_price: Money | None = None

    @field_validator('ids')
    @classmethod
    def unique_ids(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('Повторні ID не дозволені')
        return values


@router.get('/api/v1/vehicles/{id}/dismantling')
def get_workflow(id: str, db: DB, who: Auth):
    return dismantling.listing(db, id, who.user.id)


@router.post('/api/v1/vehicles/{id}/dismantling/start')
def start_workflow(id: str, db: DB, who: Auth):
    result = dismantling.start(db, id, who.user.id)
    db.commit()
    return result


@router.post('/api/v1/vehicles/{id}/dismantling/actions')
def workflow_actions(id: str, data: DismantlingAction, db: DB, who: Auth):
    result = dismantling.actions(db, id, who.user.id, data)
    db.commit()
    return result


@router.get('/api/v1/dismantling/readiness')
def readiness(db: DB, who: Auth):
    """Authenticated, read-only gate between backend and frontend Git pushes.

    Old /health=200 is insufficient: this route exists only with this contract.
    Do not expose account data or query any supplier.
    """
    from fastapi import HTTPException
    from sqlalchemy import select, text
    from sqlalchemy.exc import SQLAlchemyError
    from app.models import DismantlingItem
    from app.staging import migration_heads
    try:
        versions = frozenset(db.execute(text('SELECT version_num FROM alembic_version')).scalars())
        if versions != migration_heads():
            raise HTTPException(503, 'Dismantling schema is not at the packaged head')
        # Also catch a missing/partial table even if a revision was wrongly stamped.
        db.execute(select(DismantlingItem).limit(0))
    except SQLAlchemyError:
        raise HTTPException(503, 'Dismantling schema is not ready') from None
    return {'status':'ready', 'feature':'dismantling', 'contract_version':1,
            'required_revision':'d53c9a27f608', 'database_revisions':sorted(versions),
            'catalog_source':dismantling.CATALOG['version'],
            'catalog_items':sum(len(sub['parts']) for category in dismantling.CATALOG['categories']
                                for sub in category['subcategories'])}
