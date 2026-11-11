"""Opt-in graph editing; existing inventory/order services own every stock move."""
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import Field
from app.api.secure_route import SecureRoute
from app.api.routes import DB, Auth
from app.permissions import require_permission
from app.schemas import Input
from app.schemas.orders import Key
from app.services import assemblies as service
from app.services.inventory import owned
from app.models import DismantlingItem

router=APIRouter(route_class=SecureRoute,prefix='/api/v1/vehicles')


def gate(who,write=False,physical=False):
    require_permission(who,'vehicles.view','inventory.view')
    if physical and not service.enabled():raise HTTPException(404,'Облік складених вузлів вимкнено')
    if write:require_permission(who,'dismantling.manage','inventory.edit','inventory.adjust_quantity')


@router.get('/{id}/assemblies/readiness')
def readiness(id:str,db:DB,who:Auth):
    from app.models import Vehicle
    require_permission(who,'vehicles.view')
    owned(db,Vehicle,id,who.workspace_account_id)
    return dict(enabled=service.enabled(),workspace_enabled=True)


@router.get('/{id}/assemblies')
def tree(id:str,db:DB,who:Auth):
    gate(who)
    return service.tree(db,who.workspace_account_id,id)


@router.get('/{id}/assemblies/{item}/preview')
def preview(id:str,item:str,db:DB,who:Auth):
    gate(who)
    node=owned(db,DismantlingItem,item,who.workspace_account_id)
    if node.vehicle_id!=id:raise HTTPException(404,'Позицію цього донора не знайдено')
    result=service.preview(db,who.workspace_account_id,item)
    if 'orders.view' not in who.permissions:result['reservation_orders']=[]
    return result


class Change(Input):
    request_key: Key
    action: Literal['attach','detach','confirm','return','receipt','link_part','inspect','receipt_bulk']
    item_id: str = Field(default='',max_length=36)
    part_id: str = Field(default='',max_length=36)
    parent_id: str = Field(default='',max_length=36)
    token: str = Field(default='',max_length=64)
    sale_operation_id: str = Field(default='',max_length=36)
    include_damaged: bool = False
    presence: Literal['unchecked','present','damaged','absent'] = 'unchecked'
    quantity: int = Field(default=1,strict=True,ge=0,le=1000000)
    note: str = Field(default='',max_length=2000)
    confirm_physical: bool = False
    confirm_inventory_return_only: bool = False


@router.post('/{id}/assemblies')
def change(id:str,data:Change,db:DB,who:Auth):
    gate(who,True,physical=data.action not in ('inspect','receipt','receipt_bulk'))
    if data.action in ('attach','detach','confirm','receipt','receipt_bulk','link_part') and not data.confirm_physical:raise HTTPException(422,'Підтвердіть фізичний склад')
    if data.action=='return' and not data.confirm_inventory_return_only:raise HTTPException(422,'Підтвердіть повернення майна без автоматичного повернення коштів')
    if data.action in ('receipt','receipt_bulk'):require_permission(who,'inventory.create')
    def run():
        account=who.workspace_account_id
        if data.action=='receipt_bulk':return service.receive_confirmed(db,account,id,data)
        if data.action=='inspect':return service.inspect_item(db,account,id,data)
        if data.action=='link_part':return service.link_existing_part(db,account,id,data.part_id)
        if data.action=='receipt':return service.receive_root(db,account,id,data.item_id,data.token)
        if data.action=='attach':return service.attach(db,account,id,data.parent_id,data.item_id)
        if data.action=='detach':return service.detach(db,account,id,data.item_id)
        if data.action=='confirm':return service.confirm(db,account,id,data.item_id,data.token)
        return service.inventory_return(db,account,id,data.sale_operation_id)
    return service.command(db,who,id,'assembly:'+data.action,data,run)


class Template(Input):
    request_key: Key
    name: str = Field(min_length=1,max_length=200)
    version: int = Field(ge=1)
    provenance: str = Field(min_length=3,max_length=2000)
    template: dict


@router.post('/{id}/assemblies/templates')
def template(id:str,data:Template,db:DB,who:Auth):
    gate(who,True,physical=True)
    return service.command(db,who,id,'assembly:template',data,lambda:service.save_template(db,who.workspace_account_id,data))


class SplitComponent(Input):
    index: int = Field(strict=True,ge=0,le=50)
    condition: Literal['used','new','damaged','refurbished'] = 'used'


class SplitAssembly(Input):
    request_key: Key
    root_item_id: str = Field(min_length=1,max_length=36)
    unit_id: str = Field(min_length=2,max_length=40)
    token: str = Field(min_length=64,max_length=64)
    components: list[SplitComponent] = Field(min_length=1,max_length=20)
    confirm_physical: bool


@router.post('/{id}/assemblies/split')
def split_assembly(id:str,data:SplitAssembly,db:DB,who:Auth):
    """Physical batch split, replay protected, one atomic Part/Operation ledger."""
    gate(who,True,physical=True)
    require_permission(who,'inventory.create')
    if not data.confirm_physical:
        raise HTTPException(422,'Підтвердіть фактичне відокремлення вибраних компонентів')
    from app.services.assembly_split import split
    return service.command(db,who,id,'assembly:split',data,
        lambda:split(db,who.workspace_account_id,id,data.root_item_id,
            data.unit_id,data.components,data.token))


class DoorPlanComponent(Input):
    request_key: Key
    parent_item_id: str = Field(min_length=1,max_length=36)
    component_key: Literal['shell','glass','regulator','lock','outer-handle','inner-handle','trim','harness','seal']
    confirm: bool


@router.post('/{id}/assemblies/door-plan-components')
def add_door_plan_component(id:str,data:DoorPlanComponent,db:DB,who:Auth):
    """Plan-only admission; a physical stock move requires its own explicit workflow."""
    gate(who,True)
    if not data.confirm:raise HTTPException(422,'Підтвердіть додавання компонента до плану')
    from app.services.assembly_door_plan import add_plan_component
    return service.command(db,who,id,'assembly:door-plan',data,
                           lambda:add_plan_component(db,who.workspace_account_id,id,data.parent_item_id,data.component_key))


@router.get('/{id}/assemblies/receipt-preview')
def receipt_preview(id:str,db:DB,who:Auth,include_damaged:bool=False):
    gate(who)
    require_permission(who,'inventory.create','dismantling.manage','inventory.edit','inventory.adjust_quantity')
    return service.confirmed_receipt_preview(db,who.workspace_account_id,id,include_damaged)
