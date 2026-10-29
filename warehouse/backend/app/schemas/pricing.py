from typing import Literal
from uuid import UUID
from decimal import Decimal
from pydantic import Field,model_validator
from app.schemas import Input,Money
class PriceBatch(Input):
    ids:list[str]=Field(min_length=1,max_length=1000)
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.ids))!=len(self.ids):raise ValueError('Duplicate IDs')
        return self
class PricePreview(PriceBatch):
    mode:Literal['median','discount','markup','fixed']='median'
    percent:Decimal=Field(default=Decimal(0),ge=0,le=100,decimal_places=2)
    fixed_price:Money|None=None
    currency:Literal['UAH','USD']='UAH'
    rounding:Literal[1,10,50,100]=1
    overwrite:bool=Field(default=False,strict=True)
    request_key:UUID
    @model_validator(mode='after')
    def fixed(self):
        if (self.mode=='fixed')!=(self.fixed_price is not None):raise ValueError('Fixed mode requires a fixed price only')
        if self.mode in ('fixed','median') and self.percent:raise ValueError('Percentage applies only to discount/markup')
        return self
class PriceApply(Input):
    token:str=Field(pattern=r'^[a-f0-9]{64}$')
    confirm:bool=Field(strict=True)
    request_key:UUID
    @model_validator(mode='after')
    def explicit(self):
        if not self.confirm:raise ValueError('Потрібне явне підтвердження ціни')
        return self
