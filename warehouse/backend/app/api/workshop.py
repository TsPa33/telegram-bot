from app.api.secure_route import SecureRoute
"""Workshop projections of the existing stock ledger. No second sales ledger."""
from datetime import date, datetime, timezone
from typing import Annotated, Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import ConfigDict, Field
from sqlalchemy import select, func, or_, exists
from app.api.routes import DB, Auth
from app.models import Operation, Part, Account, Vehicle
from app.models.orders import OrderLine, Order, OrderEvent
from app.schemas import Input
from app.services.inventory import owned, snapshot, record

router = APIRouter(route_class=SecureRoute,prefix='/api/v1')

class NotesInput(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    # Compare-and-set protects against overwriting another editor's note.
    internal_notes: Annotated[str, Field(max_length=10000)]
    expected_notes: Annotated[str, Field(max_length=10000)]

class InspectionInput(Input):
    condition: Literal['unknown','used','new','damaged','refurbished'] | None = None
    availability: Literal['unchecked','present','absent','damaged'] | None = None

@router.patch('/parts/{id}/notes')
def notes(id: str, data: NotesInput, db: DB, who: Auth):
    row=owned(db,Part,id,who.workspace_account_id,lock=True,active=True)
    if row.internal_notes != data.expected_notes:
        raise HTTPException(409,'Нотатку вже змінено. Оновіть картку та порівняйте зміни.')
    before=snapshot(row);row.internal_notes=data.internal_notes
    if row.internal_notes!=before['internal_notes']:record(db,who.workspace_account_id,row,'part_update','Оновлено внутрішню нотатку',before)
    db.commit();return {**snapshot(row),'available_quantity':row.available_quantity}

@router.patch('/parts/{id}/inspection')
def inspection(id: str, data: InspectionInput, db: DB, who: Auth):
    row=owned(db,Part,id,who.workspace_account_id,lock=True,active=True);before=snapshot(row)
    if data.condition is not None:row.condition=data.condition
    if data.availability is not None:row.availability=data.availability
    if snapshot(row)!=before:record(db,who.workspace_account_id,row,'part_update','Оновлено стан / перевірку наявності',before)
    db.commit();return {**snapshot(row),'available_quantity':row.available_quantity}

@router.get('/workshop/readiness')
def readiness(db: DB, who: Auth):
    from app.api.orders import readiness as orders_readiness
    # Old inventory v5 and orders v6 stay unchanged; this is a separate capability.
    return {**orders_readiness(db,who),'contract_version':7,
        'features':['actual_quick_sale_price','ledger_sales_projection','notes_compare_and_set','inspection_patch']}

@router.get('/sales')
def sales(db: DB, who: Auth, q: str = Query('',max_length=200), vehicle_id: str | None = None,
          source: Literal['quick','order'] | None = None, date_from: datetime | None = None,
          date_to: datetime | None = None, offset: int = Query(0,ge=0), limit: int = Query(50,ge=1,le=100)):
    if date_from and date_from.tzinfo is None:date_from=date_from.replace(tzinfo=timezone.utc)
    if date_to and date_to.tzinfo is None:date_to=date_to.replace(tzinfo=timezone.utc)
    scope=select(Operation).where(Operation.account_id==who.workspace_account_id,Operation.type=='sale')
    order_sale=exists(select(OrderLine.id).where(OrderLine.account_id==who.workspace_account_id,OrderLine.sale_operation_id==Operation.id))
    if source:scope=scope.where(order_sale if source=='order' else ~order_sale)
    if vehicle_id:scope=scope.where(Operation.vehicle_id==vehicle_id)
    if date_from and date_to and date_from>date_to:raise HTTPException(422,'Некоректний період')
    if date_from:scope=scope.where(Operation.created_at>=date_from)
    if date_to:scope=scope.where(Operation.created_at<=date_to)
    if q.strip():scope=scope.where(or_(*[func.lower(Operation.after[k].as_string()).contains(q.strip().lower(),autoescape=True) for k in ('name','oem_number','article_number')]))
    total=db.scalar(select(func.count()).select_from(scope.subquery()))
    ops=list(db.scalars(scope.order_by(Operation.created_at.desc(),Operation.id).offset(offset).limit(limit)))
    from app.services.sales_projection import project_sales
    items=project_sales(db,who,ops)
    return {'items':items,'total':total,'offset':offset,'limit':limit}


@router.get('/sales/summary')
def sales_summary(db: DB, who: Auth, date_from: date, date_to: date,
                  interval: Literal['day','week','month']='day',
                  tz: Literal['Europe/Kyiv','UTC']='Europe/Kyiv', manager_id: str|None=Query(None,max_length=36)):
    from app.services.sales_analytics import summary
    if date_from>date_to or (date_to-date_from).days>=366 or date_to==date.max or date_from.year<1900 or date_to.year>2100:
        raise HTTPException(422,'Оберіть коректний період до 366 днів включно')
    from sqlalchemy.exc import DBAPIError
    try:
        return summary(db,who.workspace_account_id,date_from,date_to,interval,tz,manager_id=manager_id)
    except DBAPIError as exc:
        if getattr(exc.orig,'sqlstate',None)=='57014':
            db.rollback()
            raise HTTPException(503,'Період потребує забагато часу. Скоротіть його та повторіть запит.') from exc
        raise
