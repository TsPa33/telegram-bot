"""Version 1.5 bounded descriptor grammar. Extract facts, never infer vehicle equipment."""
import re
DIRECTION_FORMS={
 'left':{'лівої','лівого','лівих','левой','левого','левых'},
 'right':{'правої','правого','правих','правой','правых'},
 'front':{'передньої','переднього','передніх','передней','переднего','передних'},
 'rear':{'задньої','заднього','задніх','задней','заднего','задних'},
 'upper':{'верхньої','верхнього','верхней','верхнего'},
 'lower':{'нижньої','нижнього','нижней','нижнего'},
 'inner':{'внутрішньої','внутренней'},'outer':{'зовнішньої','наружной'}}
COSMETIC_FORMS={'потерт','потертості','подряпин','чистку','бордюрка'}

# Only explicit tokens. A source label is not a confirmed VehicleConfiguration.
def extract_terms(text,features):
    def take(pattern,key,convert=lambda x:x):
        nonlocal text
        values=re.findall(pattern,text)
        if values:features[key]=sorted(set(features.get(key,[])+[convert(v) for v in values]));text=re.sub(pattern,' ',text)
    take(r'\b((?:b|d)\d{4}[a-z]\d{0,3}|[bnsm]\d{2}[a-z]\d{2}[a-z0-9]{0,3})\b','engine_codes',str.upper)
    fuel={'дизельна':'diesel','дизельний':'diesel','дизельная':'diesel','дизельный':'diesel','diesel':'diesel',
          'бензинова':'petrol','бензиновий':'petrol','бензиновая':'petrol','бензиновый':'petrol','petrol':'petrol'}
    take(r'\b('+'|'.join(fuel)+r')\b','fuel_labels',fuel.get)
    take(r'\b(hev|phev|bev)\b','powertrain_labels',str.upper)
    take(r'\b(awd|fwd|rwd|4wd)\b','drive_labels',str.upper)
    take(r'\b(\d{2,3}[/xх×]\d{1,2}\s*(?:мм|mm))\b','dimensions')
    take(r'\b(перший|перша|первый|первая|другий|друга|второй|вторая|третій|третя|третий|третья)\b','ordinal_labels',
         lambda x:'1' if x in ('перший','перша','первый','первая') else '2' if x in ('другий','друга','второй','вторая') else '3')
    options={r'bowers\s*&?\s*wilkins':'bowers-wilkins',r'harman\s+kardon':'harman-kardon',r'keyless':'keyless',r'\bbsm\b':'blind-spot-monitoring',r'із захистом дітей':'child-protection',r'з підсвічуванням':'illumination'}
    for pattern,label in options.items():
        if re.search(pattern,text):features.setdefault('option_labels',[]).append(label);text=re.sub(pattern,' ',text)
    geometry={'поперечний':'transverse','поперечна':'transverse','поперечный':'transverse','поперечная':'transverse'}
    take(r'\b('+'|'.join(geometry)+r')\b','geometry',geometry.get)
    return text


def conditions_match(conditions,source,parsed):
    """Exact source-fact conditions for a reviewed rule; missing is not a match."""
    for field,required in (conditions or {}).items():
        if field=='no_conflicts':
            if parsed['conflicts']:return False
            continue
        if field in ('side_known','position_known'):
            if required and parsed[field.removesuffix('_known')]=='unknown':return False
            continue
        if field=='forbidden_positions':
            if parsed['position'] in required:return False
            continue
        actual=parsed.get('mount',[]) if field=='mount' else parsed['features'].get(field,[])
        if not required or not set(required)<=set(actual):return False
    return True


def alias_series(criteria):
    from app.services.catalogue_format import digest
    identity={k:v for k,v in criteria.items() if k not in ('installation',)}
    if not identity.get('conditions'):identity.pop('conditions',None)
    return digest(identity)
