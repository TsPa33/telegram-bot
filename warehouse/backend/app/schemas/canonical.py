from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

class SourceConditions(BaseModel):
    """All-of conditions on explicitly observed SOURCE facts, not vehicle fitment."""
    model_config=ConfigDict(extra='forbid')
    fuel_labels:list[Literal['petrol','diesel']]|None=Field(default=None,max_length=2)
    powertrain_labels:list[Literal['HEV','PHEV','BEV']]|None=Field(default=None,max_length=3)
    engine_codes:list[str]|None=Field(default=None,max_length=10)
    engine_labels:list[str]|None=Field(default=None,max_length=10)
    drive_labels:list[Literal['AWD','FWD','RWD','4WD']]|None=Field(default=None,max_length=4)
    technology:list[str]|None=Field(default=None,max_length=10)
    option_labels:list[str]|None=Field(default=None,max_length=20)
    side_known:Literal[True]|None=None
    position_known:Literal[True]|None=None
    no_conflicts:Literal[True]|None=None
    mount:list[Literal['upper','lower','inner','outer']]|None=Field(default=None,max_length=4)
    forbidden_positions:list[Literal['front','rear','unknown']]|None=Field(default=None,max_length=3)
    assembly:list[Literal['complete','bare']]|None=Field(default=None,max_length=2)
    @model_validator(mode='after')
    def bounded(self):
        for key,value in self.model_dump(exclude_none=True).items():
            if isinstance(value,list):
                if not value or any(not v or len(v)>100 or any(ord(c)<32 for c in v) for v in value):raise ValueError('Умови мають містити явні непорожні значення')
                setattr(self,key,sorted(set(value)))
        return self

class GroupRuleInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    type_id:str=Field(min_length=1,max_length=36)
    phrase:str=Field(min_length=1,max_length=1000)
    category:str=Field(min_length=1,max_length=200)
    subcategory:str=Field(min_length=1,max_length=200)
    manufacturer:str=Field(default='',max_length=100)
    model:str=Field(default='',max_length=100)
    conditions:SourceConditions=Field(default_factory=SourceConditions)
    expected_revision:int=Field(default=0,ge=0,strict=True)
    evidence:str=Field(min_length=5,max_length=2000)

class GroupApprovalInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    preview_id:str=Field(min_length=1,max_length=36)
    token:str=Field(pattern=r'^[a-f0-9]{64}$')
    confirm:bool=Field(strict=True)
