"""Offline adapter contract. No VIN lookup, network or invented build-sheet facts."""
import re
from typing import Protocol
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.schemas.vehicle_configuration import ConfigurationFact
class DecodeResult(BaseModel):
    model_config=ConfigDict(extra='forbid')
    vin:str
    adapter:str
    version:str
    facts:list[ConfigurationFact]=Field(default_factory=list)
    complete:bool=False
    @field_validator('vin')
    @classmethod
    def vin_format(cls,value):
        value=value.strip().upper()
        if not re.fullmatch('[A-HJ-NPR-Z0-9]{17}',value):raise ValueError('VIN має містити 17 допустимих символів')
        return value
    @field_validator('facts')
    @classmethod
    def reported_only(cls,value):
        if any(f.kind!='vin_decode' or f.confidence!='reported' for f in value):raise ValueError('Decoder attributes require separate human/document review')
        return value
class VinAdapter(Protocol):
    def decode(self,vin:str)->DecodeResult:...
class OfflineVinAdapter:
    def decode(self,vin:str)->DecodeResult:
        return DecodeResult(vin=vin,adapter='offline-no-lookup',version='1',facts=[],complete=False)
