"""Existing free VIN sources, independently attempted; never infer missing facts."""
import json
import re
from datetime import datetime, timezone
from urllib.request import Request,urlopen
from app.services.vin_normalize import normalize,merge_verified,validate_consistency

VPIC_FIELDS={'Make':'manufacturer','Model':'model','ModelYear':'year','EngineModel':'engine','DisplacementL':'engine_displacement_l','FuelTypePrimary':'fuel_type','TransmissionStyle':'transmission','DriveType':'drive_type','BodyClass':'body_class','Trim':'trim','PlantCountry':'plant_country','EngineCylinders':'engine_cylinders','EngineKW':'engine_power_kw','Doors':'doors','EngineHP':'engine_power_hp','Series':'series','VehicleType':'vehicle_type','PlantCity':'plant_city'}


def lookup(vin):
    if not re.fullmatch('[A-HJ-NPR-Z0-9]{17}',vin):raise ValueError('Invalid VIN')
    vehicle={};sources=[];conflicts={};errors=[];provenance={}
    try:
        url='https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/'+vin+'?format=json'
        with urlopen(Request(url,headers={'User-Agent':'CarPotWarehouse/1.0','Accept':'application/json'}),timeout=7) as response:
            body=response.read(160001)
            if len(body)>160000:raise ValueError('Response too large')
            row=json.loads(body)['Results'][0]
        incoming={target:str(row.get(key) or '').strip() for key,target in VPIC_FIELDS.items()}
        incoming={k:v for k,v in incoming.items() if v.casefold() not in ('','null','none','not applicable','0')}
        year=incoming.get('year','')
        if not (incoming.get('model') and year.isdigit() and 1886<=int(year)<=2100) or str(row.get('ErrorCode','')).startswith(('5','6','7')):incoming.pop('year',None)
        if incoming.get('year'):incoming['year']=int(incoming['year'])
        vehicle=normalize(incoming)
        if vehicle:sources.append('NHTSA vPIC');provenance.update({k:'NHTSA vPIC' for k in vehicle})
    except (OSError,ValueError,KeyError,IndexError,TypeError):errors.append('NHTSA vPIC unavailable')
    # Paid/credentialed Vincario is deliberately not called by the quick-add flow.
    if not all(vehicle.get(k) for k in ('model','year','engine','transmission')):
        from app.services.vin_freevindecoder import decode_page
        try:
            incoming=decode_page(vin)
            if incoming:
                prior=dict(vehicle);vehicle,new_conflicts=merge_verified(vehicle,incoming);conflicts.update(new_conflicts);sources.append('FreeVINDecoder')
                provenance.update({k:'FreeVINDecoder' for k,v in incoming.items() if v not in ('',None) and not prior.get(k)})
        except (OSError,ValueError,TypeError):errors.append('FreeVINDecoder unavailable')
    return dict(vin=vin,source=' + '.join(sources) or 'unavailable',vehicle=vehicle,
        available_fields=[k for k,v in vehicle.items() if v not in ('',None)],field_sources=provenance,
        conflicts=conflicts,consistency_issues=validate_consistency(vehicle),requires_review=True,
        observed_at=datetime.now(timezone.utc).isoformat(),live_data_received=bool(vehicle),
        message='Перевірте знайдені характеристики. Невизначені поля можна заповнити вручну.' if vehicle else 'Декодери недоступні або не знайшли даних. Додайте автомобіль вручну.')
