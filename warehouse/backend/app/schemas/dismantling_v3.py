from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from app.schemas import Input
from app.schemas.vehicle_configuration import ConfigurationPreview
class Resolution(Input):
    action:Literal['link','new','skip']
    item_id:str|None=Field(default=None,max_length=36)
    reason:str=Field(min_length=3,max_length=1000)
    @model_validator(mode='after')
    def consistent(self):
        if (self.action=='link')!=bool(self.item_id):raise ValueError('Link requires exactly one existing item')
        return self
class PlanPreview(ConfigurationPreview):
    reset_trial:bool=Field(default=False,strict=True)
    resolutions:dict[str,Resolution]=Field(default_factory=dict,max_length=2000)
class PlanSave(PlanPreview):
    token:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:UUID
    confirm:bool=Field(strict=True)
class PlanDecision(Input):
    ids:list[str]=Field(min_length=1,max_length=1000)
    action:Literal['present','absent','not_applicable','unchecked','exclude','restore','dismantled','receipt']
    reason:str=Field(default='',max_length=1000)
    etag:str=Field(pattern=r'^[a-f0-9]{64}$')
    request_key:UUID
    confirm:bool=Field(default=False,strict=True)
    quantity:int=Field(default=1,ge=1,le=1000000,strict=True)
    condition:Literal['used','new','damaged','refurbished']|None=None
    location:str=Field(default='',max_length=120)
    @model_validator(mode='after')
    def valid(self):
        if len(set(self.ids))!=len(self.ids):raise ValueError('Duplicate item IDs')
        if self.action in ('exclude','absent','not_applicable') and len(self.reason.strip())<3:raise ValueError('Потрібна причина виключення')
        if self.action in ('receipt','dismantled') and not self.confirm:raise ValueError('Потрібне явне підтвердження дії')
        return self

class PlanQuick(PlanPreview):
    """Explicit atomic command; no separate preview required for automatic choices."""
    request_key:UUID
    etag:str=Field(pattern=r'^[a-f0-9]{64}$')
    confirm:bool=Field(strict=True)
    token:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    @model_validator(mode='after')
    def reviewed(self):
        if not self.confirm:raise ValueError('Потрібна явна дія створення або оновлення плану')
        if self.resolutions and not self.token:raise ValueError('Ручні рішення потребують перевіреного preview')
        return self
