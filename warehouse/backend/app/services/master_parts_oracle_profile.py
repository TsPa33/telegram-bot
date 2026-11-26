"""Normalize known Oracle identity attributes, not physical/VIN fitment.
Never infer door counts, dual wheels, equipment, or exact drive axle from body/model names.
"""
from collections import defaultdict
import re


def oracle_profile(data, *, expected_kind, expected_car_id):
    if (data.get('source')!='oracle' or data.get('kind')!=expected_kind
            or data.get('source_modification_id')!=expected_car_id
            or data.get('truncated') is not False or data.get('vehicle_identity_only') is not True
            or data.get('fitment_verified') is not False or not isinstance(data.get('items'),list)):
        raise ValueError('Unverified or incomplete Oracle attribute response')
    groups=defaultdict(set)
    for item in data['items']:
        name=item.get('attribute_type'); value=item.get('display_value')
        if isinstance(name,str) and isinstance(value,str) and value.strip():groups[name].add(value.strip().casefold())
    p={'kind':'passenger' if expected_kind=='passenger' else None,'flags':{},'counts':{}}
    missing=[]; conflicts=[]; source_facts={}
    def one(key):
        values=groups.get(key,set())
        if len(values)==1:
            v=next(iter(values));source_facts[key]=v;return v
        if len(values)>1:conflicts.append(key)
        return None
    engine=one('EngineType'); fuel=one('FuelType')
    if engine:
        if engine in ('бензиновый двигатель','дизель','дизельный двигатель'):
            p['flags']['ice']=True
            kind='diesel' if 'дизель' in engine else 'petrol'
            fkind={'бензин':'petrol','бензин/этанол':'petrol','дизель':'diesel','дизельное топливо':'diesel'}.get(fuel)
            if fuel is None or fkind==kind:p['fuel']=kind
            elif fkind and fkind!=kind:conflicts.append('fuel_engine')
    cylinders=one('NumberOfCylinders')
    if cylinders and re.fullmatch(r'[1-9][0-9]?',cylinders) and int(cylinders)<=32:p['counts']['cylinders']=int(cylinders)
    body=one('BodyType')
    if body in ('седан','купе','хэтчбек','хетчбэк','кабриолет'):
        p['body']={'седан':'sedan','купе':'coupe','хэтчбек':'hatch','хетчбэк':'hatch','кабриолет':'convertible'}[body]
    # Oracle body classifications such as универсал / вездеход закрытый do not prove door topology.
    platform=one('PlatformType'); config=one('AxleConfiguration')
    if expected_kind=='commercial' and platform=='седельный тягач':
        p['kind']='heavy_truck';p['body']='tractor';p['rear_closure']='none'
        if config in ('4x2','4x4','6x2','6x4','6x6','8x2','8x4','8x6','8x8'):
            p['axles']=[{} for _ in range(int(config[0])//2)]
            for i,a in enumerate(p['axles'],1):
                values={v.split('/',1)[1].strip() for v in groups.get('Suspension',set()) if re.match(rf'^\s*{i}\s*/',v)}
                if len(values)==1:
                    value=next(iter(values))
                    if value=='пневматическая рессора':a['air_suspension']=True
                    elif value in ('параболическая рессора','листовая рессора'):a['leaf_spring']=True
                elif len(values)>1:conflicts.append(f'axle:{i}:suspension_alternatives')
    mixture=one('FuelMixture')
    if mixture=='непосредственный впрыск':p['flags'].update(direct_injection=True,injection=True)
    brake=one('BrakeSystem')
    if brake=='гидравлический':p['flags']['hydraulic_brakes']=True
    elif brake=='пневматический':p['flags']['air_brakes']=True
    one('DriveType') # retained as evidence, not converted into precise driven-axle indexes
    for key in ('powertrain','body','side_doors','rear_closure','axles','transmission','positions','door_features'):
        if key not in p:missing.append(key)
    return {'profile':p,'source_facts':source_facts,'missing':missing,'conflicts':conflicts,'source_modification_id':expected_car_id,'source_kind':expected_kind,'fitment_verified':False}
