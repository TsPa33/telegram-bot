from app.api.secure_route import SecureRoute
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query
from pydantic import Field, field_validator, model_validator
from sqlalchemy.orm import Session
from app.api.deps import Identity, identity
from app.db import get_db
from app.schemas import Input, Money
from app.services import dismantling

router = APIRouter(route_class=SecureRoute,tags=['Dismantling'])
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
    return dismantling.listing(db, id, who.workspace_account_id)


@router.post('/api/v1/vehicles/{id}/dismantling/start')
def start_workflow(id: str, db: DB, who: Auth):
    result = dismantling.start(db, id, who.workspace_account_id)
    db.commit()
    return result


@router.post('/api/v1/vehicles/{id}/dismantling/actions')
def workflow_actions(id: str, data: DismantlingAction, db: DB, who: Auth):
    result = dismantling.actions(db, id, who.workspace_account_id, data)
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
            'required_revision':'c24a9b71e603', 'database_revisions':sorted(versions),
            'catalog_source':dismantling.CATALOG['version'],
            'catalog_items':sum(len(sub['parts']) for category in dismantling.CATALOG['categories']
                                for sub in category['subcategories'])}


class Scope(Input):
    source: Annotated[str,Field(min_length=1,max_length=100)] | None = None
    category_key: Annotated[str,Field(min_length=1,max_length=100)] | None = None
    subcategory_key: Annotated[str,Field(min_length=1,max_length=100)] | None = None

    @model_validator(mode='after')
    def hierarchy_scope(self):
        if self.subcategory_key and not self.category_key:raise ValueError('Підкатегорія потребує категорії')
        if self.category_key and not self.source:raise ValueError('Категорія потребує джерела')
        return self


class PlanUpdate(Scope):
    ids: Annotated[list[str],Field(min_length=1,max_length=1000)] | None = None
    included: Annotated[bool,Field(strict=True)]

    @field_validator('ids')
    @classmethod
    def unique(cls,value):
        if value is not None and len(set(value))!=len(value):raise ValueError('Повторні ID')
        return value

    @model_validator(mode='after')
    def scope_valid(self):
        if self.ids is not None:
            if self.source or self.category_key or self.subcategory_key:raise ValueError('ID або категорія, не обидва')
        elif not self.source or not self.category_key:raise ValueError('Для масової зміни потрібні джерело й категорія')
        return self


class BatchAction(Scope):
    action: Literal['dismantled','receipt']
    q: Annotated[str,Field(max_length=200)] = ''
    selection_token: Annotated[str,Field(pattern=r'^[a-f0-9]{64}$')]
    expected_count: Annotated[int,Field(strict=True,ge=1,le=1000)]
    quantity: Annotated[int,Field(strict=True,ge=1,le=1000000)] = 1
    condition: Literal['used','new','damaged','refurbished'] | None = None
    location: Annotated[str,Field(max_length=120)] = ''
    selling_price: Money | None = None


class ApplicableModel(Input):
    manufacturer: Annotated[str, Field(min_length=1,max_length=100)]
    model: Annotated[str, Field(min_length=1,max_length=100)]
    generation: Annotated[str, Field(max_length=100)] = ''


class CatalogTypeInput(Input):
    catalog_key: Annotated[str,Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,99}$')]
    category_key: Annotated[str,Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,99}$')]
    category_name: Annotated[str,Field(min_length=1,max_length=100)]
    subcategory_key: Annotated[str,Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,99}$')]
    subcategory_name: Annotated[str,Field(min_length=1,max_length=100)]
    name: Annotated[str,Field(min_length=1,max_length=200)]
    position: Annotated[str,Field(max_length=100)] = ''

    @model_validator(mode='after')
    def stock_label_fits(self):
        if len(self.name+(' · '+self.position if self.position else ''))>200:
            raise ValueError('Назва разом із розташуванням має вміститися у 200 символів складської позиції')
        return self


class CatalogImport(Input):
    source: Annotated[str,Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,99}$')]
    provenance: Annotated[str,Field(min_length=3,max_length=2000)]
    license_reference: Annotated[str,Field(min_length=3,max_length=2000)]
    rights_confirmed: Annotated[bool,Field(strict=True)]
    types: Annotated[list[CatalogTypeInput],Field(min_length=1,max_length=10000)]

    @model_validator(mode='after')
    def valid_source(self):
        if self.source.startswith('carpot.') or not self.rights_confirmed:raise ValueError('Потрібне власне джерело та підтверджені права')
        if len({r.catalog_key for r in self.types})!=len(self.types):raise ValueError('Повторні ключі типів')
        return self


@router.get('/api/v1/vehicles/{id}/dismantling/workspace')
def workspace(id: str,db: DB,who: Auth,offset: int=Query(0,ge=0),limit: int=Query(100,ge=1,le=200),
              q: str=Query('',max_length=200),source: str | None=Query(None,max_length=100),
              category_key: str | None=Query(None,max_length=100),subcategory_key: str | None=Query(None,max_length=100),
              visibility: Literal['all','included','excluded']='all'):
    return dismantling.workspace(db,id,who.workspace_account_id,offset=offset,limit=limit,q=q,source=source,
        category_key=category_key,subcategory_key=subcategory_key,visibility=visibility)


@router.post('/api/v1/vehicles/{id}/dismantling/plan')
def plan(id: str,data: PlanUpdate,db: DB,who: Auth):
    result=dismantling.change_plan(db,id,who.workspace_account_id,data);db.commit();return result


@router.post('/api/v1/vehicles/{id}/dismantling/batch')
def batch(id: str,data: BatchAction,db: DB,who: Auth):
    result=dismantling.batch(db,id,who.workspace_account_id,data);db.commit();return result


@router.post('/api/v1/dismantling/catalog/import')
def import_catalog(data: CatalogImport,db: DB,who: Auth,dry_run: bool=False):
    from app.services.dismantling_catalog import import_catalog as apply
    result=apply(db,who.workspace_account_id,data,dry_run)
    if not dry_run:db.commit()
    return result


@router.get('/api/v1/dismantling/workspace-readiness')
def workspace_readiness(db: DB,who: Auth):
    from fastapi import HTTPException
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError
    from app.models import DismantlingCatalogSource,DismantlingCatalogType
    result=readiness(db,who)
    try:
        db.execute(select(DismantlingCatalogSource).limit(0));db.execute(select(DismantlingCatalogType).limit(0))
    except SQLAlchemyError:raise HTTPException(503,'Local catalogue schema is not ready') from None
    return {**result,'contract_version':2,'required_revision':'c24a9b71e603',
            'features':['persistent_plan','paginated_catalog','confirmed_receipt','account_catalog_import']}


class AddStock(Input):
    selection_token: Annotated[str,Field(pattern=r'^[a-f0-9]{64}$')]
    expected_count: Annotated[int,Field(strict=True,ge=1,le=10000)]
    # UX 3.0 confirms one of each; later quantity edits use the stock ledger.
    quantity: Literal[1] = 1
    condition: Literal['used','new','damaged','refurbished'] | None = None
    location: Annotated[str,Field(max_length=120)] = ''
    selling_price: Money | None = None


@router.post('/api/v1/vehicles/{id}/dismantling/prepare')
def prepare(id: str,db: DB,who: Auth):
    # Explicit authenticated/CSRF-protected POST. GETs remain strictly read-only.
    from app.models import Vehicle
    from app.services.inventory import owned
    vehicle=owned(db,Vehicle,id,who.workspace_account_id,lock=True)
    result={'created':0} if vehicle.archived else dismantling.start(db,id,who.workspace_account_id)
    db.commit()
    return result


@router.post('/api/v1/vehicles/{id}/dismantling/add-stock')
def add_stock(id: str,data: AddStock,db: DB,who: Auth):
    result=dismantling.add_stock(db,id,who.workspace_account_id,data)
    db.commit()
    return result


@router.get('/api/v1/dismantling/simple-readiness')
def simple_readiness(db: DB,who: Auth):
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError
    from fastapi import HTTPException
    from app.models import Vehicle
    result=workspace_readiness(db,who)
    try:db.execute(select(Vehicle.number).limit(0))
    except SQLAlchemyError:raise HTTPException(503,'Vehicle numbers are not ready') from None
    return {**result,'contract_version':3,
        'features':result['features']+['automatic_catalog','direct_confirmed_receipt','account_vehicle_number']}
