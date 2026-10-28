from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
FIELDS={'manufacturer','model','generation','year','engine_code','fuel_type','powertrain','transmission','drive','body_type','options','options_complete','vin'}
class ConfigurationFact(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    field:Literal['manufacturer','model','generation','year','engine_code','fuel_type','powertrain','transmission','drive','body_type','options','options_complete','vin']
    value:str|int|bool|list[str]
    kind:Literal['manual','document','vin_decode']
    reference:str=Field(min_length=3,max_length=2000)
    confidence:Literal['reported','verified']='reported'
    @model_validator(mode='after')
    def valid_value(self):
        import re
        if self.kind=='vin_decode' and self.confidence=='verified':raise ValueError('VIN-відповідь є пропозицією; потрібне ручне або документальне підтвердження')
        if self.field=='options_complete':
            if not isinstance(self.value,bool) or self.kind!='document' or self.confidence!='verified':raise ValueError('Повнота опцій потребує явного перевіреного документа')
        elif self.field=='year':
            if isinstance(self.value,bool) or not isinstance(self.value,int) or not 1886<=self.value<=2100:raise ValueError('Неправильний рік')
        elif self.field=='options':
            if not isinstance(self.value,list) or len(self.value)>100 or any(not x or len(x)>100 for x in self.value):raise ValueError('Опції — явні коди, не припущення')
            self.value=sorted(set(self.value))
        elif not isinstance(self.value,str) or not self.value or len(self.value)>200:raise ValueError('Потрібне непорожнє текстове значення')
        if self.field=='powertrain' and self.value not in ('petrol','diesel','HEV','PHEV','BEV'):raise ValueError('Невідомий тип силової установки')
        if self.field=='fuel_type' and self.value not in ('petrol','diesel','electric','other'):raise ValueError('Невідомий тип пального')
        if self.field=='drive' and self.value not in ('AWD','FWD','RWD','4WD'):raise ValueError('Невідомий привід')
        if self.field=='vin' and not re.fullmatch('[A-HJ-NPR-Z0-9]{17}',self.value.upper()):raise ValueError('Неправильний VIN')
        if isinstance(self.value,str) and any(ord(c)<32 for c in self.value):raise ValueError('Control characters')
        return self
class ConfigurationPreview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    facts:list[ConfigurationFact]=Field(max_length=200)
    selected:dict[str,int]=Field(default_factory=dict,max_length=12)
class ConfigurationConfirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    preview_id:str=Field(max_length=36)
    token:str=Field(pattern=r'^[a-f0-9]{64}$')
    confirm:bool=Field(strict=True)
