"""Two bounded free sources, field provenance, conservative merging and short cache."""
from copy import deepcopy
import hashlib
import json
import re
from datetime import datetime,timezone
from threading import Lock
from time import monotonic
from urllib.request import Request,urlopen
from app.services.vin_normalize import normalize,merge_verified,validate_consistency,ukrainian,equivalent
from app.services.vin_fields import PRIMARY,EXTRA,PRIMARY_KEYS,EXTRA_KEYS,IMPORTANT,CATALOGUE_KEYS,present

VPIC_FIELDS=PRIMARY  # Existing adapter test compatibility.
_cache={};_cache_guard=Lock();_locks=tuple(Lock() for _ in range(16))


def clear_cache():
    with _cache_guard:_cache.clear()


def _lookup(vin):
    vehicle={};additional={};sources=[];conflicts={};provenance={};provider_status={};counts={};diagnostics={};year_uncertain=False
    try:
        url='https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/'+vin+'?format=json'
        with urlopen(Request(url,headers={'User-Agent':'CarPotWarehouse/1.0','Accept':'application/json'}),timeout=7) as response:
            body=response.read(160001)
            if len(body)>160000:raise ValueError('Response too large')
            row=json.loads(body)['Results'][0]
        if not isinstance(row,dict):raise ValueError('Invalid provider response')
        counts['nhtsa_nonempty_fields']=sum(present(v) for k,v in row.items() if k not in ('VIN','ErrorText','ErrorCode','SuggestedVIN'))
        incoming={target:str(row[key]).strip() for key,target in PRIMARY.items() if present(row.get(key)) and len(str(row[key]))<=200}
        # Zero is meaningful for doors/electrification/battery, but not for model year/displacement.
        for key in ['year','engine_displacement_l','engine_power_kw','engine_power_hp']:
            if incoming.get(key) in ('0','0.0'):incoming.pop(key,None)
        year=incoming.get('year','')
        errors={e.strip() for e in str(row.get('ErrorCode','')).split(',')}
        if not (incoming.get('model') and year.isdigit() and 1886<=int(year)<=2100) or errors.intersection({'5','6','7'}):incoming.pop('year',None)
        error_text=str(row.get('ErrorText','')).casefold()
        year_uncertain='10' in errors or ('model year' in error_text and any(word in error_text for word in ('ambiguous','unable','cannot','not be valid','multiple')))
        if year_uncertain:
            diagnostics['year_observation']={'reported_year':incoming.pop('year',None),'reason':'provider_model_year_uncertain','codes':sorted(e for e in errors if e.isdigit())}
        if incoming.get('year'):incoming['year']=int(incoming['year'])
        vehicle=normalize(incoming)
        for source_key,(key,label) in EXTRA.items():
            if present(row.get(source_key)) and len(str(row[source_key]))<=200:
                additional[key]={'label':label,'value':ukrainian(key,row[source_key]),'source':'NHTSA vPIC'}
        provider_status['NHTSA vPIC']='reported' if vehicle or additional else 'empty'
        if vehicle or additional:sources.append('NHTSA vPIC');provenance.update({k:'NHTSA vPIC' for k in vehicle})
    except (OSError,ValueError,KeyError,IndexError,TypeError):provider_status['NHTSA vPIC']='unavailable_or_invalid_response'
    missing=sorted(k for k in IMPORTANT if not present(vehicle.get(k)))
    if missing:
        from app.services.vin_freevindecoder import decode_page,source_status
        try:
            incoming=decode_page(vin)
            if incoming:
                incoming_extra=incoming.get('additional',{})
                incoming={k:v for k,v in incoming.items() if k in PRIMARY_KEYS and present(v) and len(str(v))<=200}
                prior=dict(vehicle);vehicle,new_conflicts=merge_verified(vehicle,incoming);conflicts.update(new_conflicts)
                for key,attribute in incoming_extra.items():
                    if key not in EXTRA_KEYS or not isinstance(attribute,dict) or not present(attribute.get('value')) or len(str(attribute['value']))>200:continue
                    value=ukrainian(key,attribute['value'])
                    if key in additional:
                        if not equivalent(key,additional[key]['value'],value):additional[key].update(alternative=value,alternative_source='FreeVINDecoder')
                    else:
                        label=next(label for k,label in EXTRA.values() if k==key)
                        additional[key]={'label':label,'value':value,'source':'FreeVINDecoder'}
                if incoming or incoming_extra:sources.append('FreeVINDecoder')
                provenance.update({k:'FreeVINDecoder' for k,v in incoming.items() if not present(prior.get(k))})
                provider_status['FreeVINDecoder']='reported' if incoming or incoming_extra else 'empty'
            else:provider_status['FreeVINDecoder']=source_status(vin)
        except (OSError,ValueError,TypeError):provider_status['FreeVINDecoder']='unavailable_or_invalid_response'
    else:provider_status['FreeVINDecoder']='not_needed'
    missing=sorted(k for k in IMPORTANT if not present(vehicle.get(k)))
    issues=validate_consistency(vehicle)
    if year_uncertain:issues['year']='Джерело не визначило рік однозначно. Перевірте рік автомобіля перед збереженням.'
    return dict(diagnostics=diagnostics,vin=vin,source=' + '.join(sources) or 'unavailable',vehicle=vehicle,additional=additional,
        available_fields=[k for k,v in vehicle.items() if present(v)],field_sources=provenance,
        conflicts=conflicts,consistency_issues=issues,requires_review=True,
        observed_at=datetime.now(timezone.utc).isoformat(),live_data_received=bool(vehicle or additional),
        missing_fields=missing,provider_status=provider_status,
        counts={**counts,'received_useful':len(vehicle)+len(additional),'catalogue_useful':sum(k in CATALOGUE_KEYS for k in vehicle)+len(additional),'undefined_important':len(missing),'undefined_supported':sum(not present(vehicle.get(k)) for k in PRIMARY_KEYS),'conflicting':len(conflicts)+sum('alternative' in a for a in additional.values())},
        message='Перевірте знайдені характеристики. Невизначені поля можна уточнити.' if vehicle else 'Джерела недоступні або не знайшли даних. Додайте автомобіль вручну.')


def lookup(vin):
    vin=vin.strip().upper()
    if not re.fullmatch('[A-HJ-NPR-Z0-9]{17}',vin):raise ValueError('Invalid VIN')
    with _locks[int(hashlib.sha256(vin.encode()).hexdigest()[:8],16)%len(_locks)]:
        now=monotonic()
        with _cache_guard:entry=_cache.get(vin)
        if entry and entry[0]>now:return {**deepcopy(entry[1]),'cached':True}
        result=_lookup(vin)
        with _cache_guard:
            if len(_cache)>=128:_cache.pop(next(iter(_cache)))
            _cache[vin]=(monotonic()+(300 if result['live_data_received'] else 30),deepcopy(result))
        return {**result,'cached':False}
