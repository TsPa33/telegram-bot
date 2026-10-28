from fastapi import APIRouter,HTTPException
from sqlalchemy import text
from app.api.catalogue import DB,Auth
from app.api.secure_route import SecureRoute
from app.models import Vehicle
from app.services.inventory import owned
from app.services import dismantling_plan_v3 as service
from app.schemas.dismantling_v3 import PlanPreview,PlanSave,PlanDecision
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
