from fastapi import APIRouter,HTTPException
from app.api.catalogue import DB,Auth
from app.api.secure_route import SecureRoute
from app.models import Vehicle
from app.services.inventory import owned
from app.services import vehicle_configuration as service
from app.schemas.vehicle_configuration import ConfigurationPreview,ConfigurationConfirm
router=APIRouter(route_class=SecureRoute,tags=['VIN-ready vehicle configuration'])
@router.get('/api/v1/vehicles/{id}/configuration')
def read_configuration(id:str,db:DB,who:Auth):
    v=owned(db,Vehicle,id,who.workspace_account_id)
    return {'configuration':service.latest(db,v,who.workspace_account_id),'contract_version':1,'decoder_integrated':False}
@router.post('/api/v1/vehicles/{id}/configuration/preview')
def preview_configuration(id:str,data:ConfigurationPreview,db:DB,who:Auth):
    v=owned(db,Vehicle,id,who.workspace_account_id)
    return service.summary(service.preview(db,v,who,[f.model_dump() for f in data.facts],data.selected))
@router.post('/api/v1/vehicles/{id}/configuration/confirm')
def confirm_configuration(id:str,data:ConfigurationConfirm,db:DB,who:Auth):
    if not data.confirm:raise HTTPException(422,'Потрібне явне підтвердження конфігурації')
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True)
    return service.summary(service.confirm(db,v,who,data.preview_id,data.token))
