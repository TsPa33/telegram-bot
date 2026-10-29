from fastapi import APIRouter,HTTPException,Query
from sqlalchemy import text
from app.api.catalogue import DB,Auth
from app.api.secure_route import SecureRoute
from app.models import Vehicle
from app.services.inventory import owned
from app.services import dismantling_plan_v3 as service
from app.schemas.dismantling_v3 import PlanPreview,PlanSave,PlanDecision,PlanQuick,BulkSelection,BulkCommand
from app.services.catalogue_import import LOCK
router=APIRouter(route_class=SecureRoute,tags=['Managed dismantling plan v3'])
@router.get('/api/v1/vehicles/{id}/dismantling-v3')
def read(id:str,db:DB,who:Auth):return service.listing(db,owned(db,Vehicle,id,who.workspace_account_id))
@router.post('/api/v1/vehicles/{id}/dismantling-v3/preview')
def preview(id:str,data:PlanPreview,db:DB,who:Auth):return service.make_preview(db,owned(db,Vehicle,id,who.workspace_account_id),who,data)
@router.post('/api/v1/vehicles/{id}/dismantling-v3/save')
def save(id:str,data:PlanSave,db:DB,who:Auth):
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    cached,_=service.replay(db,v,who,data,'save')
    if cached is not None:return cached
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK}):raise HTTPException(409,'Каталог оновлюється; повторіть збереження після завершення операції')
    result=service.save(db,v,who,data);db.commit();return result
@router.post('/api/v1/vehicles/{id}/dismantling-v3/decisions')
def decisions(id:str,data:PlanDecision,db:DB,who:Auth):
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    result=service.decide(db,v,who,data);db.commit();return result

@router.post('/api/v1/vehicles/{id}/dismantling-v3/quick')
def quick(id:str,data:PlanQuick,db:DB,who:Auth):
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    cached,_=service.replay(db,v,who,data,'quick')
    if cached is not None:return cached
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK}):raise HTTPException(409,'Каталог оновлюється; повторіть формування після завершення операції')
    result=service.quick(db,v,who,data);db.commit();return result

@router.get('/api/v1/vehicles/{id}/dismantling-v3/selection')
def selection(id:str,db:DB,who:Auth,q:str=Query('',max_length=200),category:str=Query('',max_length=100),subcategory:str=Query('',max_length=100),status:str=Query('all',max_length=50),offset:int=Query(0,ge=0),limit:int=Query(1000,ge=1,le=1000)):
    from app.services.dismantling_bulk import select_ids
    return select_ids(db,owned(db,Vehicle,id,who.workspace_account_id),q=q,category=category,subcategory=subcategory,status=status,offset=offset,limit=limit)

@router.post('/api/v1/vehicles/{id}/dismantling-v3/bulk/preview')
def bulk_preview(id:str,data:BulkSelection,db:DB,who:Auth):
    from app.services.dismantling_bulk import preview
    return preview(db,owned(db,Vehicle,id,who.workspace_account_id),data.ids,data.action)

@router.post('/api/v1/vehicles/{id}/dismantling-v3/bulk')
def bulk_command(id:str,data:BulkCommand,db:DB,who:Auth):
    from app.services.dismantling_bulk import execute
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    result=execute(db,v,who,data);db.commit();return result

from app.services import virtual_inventory as virtual
from app.schemas.dismantling_v3 import VirtualAvailability

@router.get('/api/v1/vehicles/{id}/virtual-dismantling')
def virtual_read(id:str,db:DB,who:Auth):
    return virtual.listing(db,owned(db,Vehicle,id,who.workspace_account_id))

@router.post('/api/v1/vehicles/{id}/virtual-dismantling/activate')
def virtual_activate(id:str,data:PlanQuick,db:DB,who:Auth):
    virtual.lock_workspace(db,who.workspace_account_id)
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    old,_=service.replay(db,v,who,data,'virtual_activation')
    if old is not None:return old
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK}):raise HTTPException(409,'Каталог оновлюється; повторіть після завершення')
    result=virtual.activate(db,v,who,data);db.commit();return result

@router.post('/api/v1/vehicles/{id}/virtual-dismantling/availability')
def virtual_availability(id:str,data:VirtualAvailability,db:DB,who:Auth):
    virtual.lock_workspace(db,who.workspace_account_id)
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    result=virtual.availability(db,v,who,data);db.commit();return result
