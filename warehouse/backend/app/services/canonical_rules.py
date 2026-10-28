"""Conservative full-phrase normalization. OEM never establishes function/fitment."""
import json
import re
import unicodedata
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from app.services.catalogue_format import digest
from app.services.aleto_import import CATEGORY_ALIASES
DATA=Path(__file__).resolve().parents[1]/'data'
BASE=json.loads((DATA/'dismantling_catalog.json').read_text())
RULES=json.loads((DATA/'canonical_rules_v1.json').read_text())

def norm(s):return ' '.join(re.sub(r'[^\w]+',' ',unicodedata.normalize('NFKC',s or '').casefold()).split())
def sid(*values):return str(uuid5(NAMESPACE_URL,'carpot.canonical.v3:'+digest(values)))
def type_record(name,category,subcategory,provenance=None):
    key=digest([norm(category),norm(subcategory),norm(name)])
    return dict(id=sid('type',key),identity_key=key,name=name,category=category,subcategory=subcategory,provenance=provenance or {'rule_version':RULES['version']})

DIRECTIONS={
 'left':{'лівий','ліва','ліве','ліві','лів','левый','левая','левое','левые','лев','left','lh'},
 'right':{'правий','права','праве','праві','правый','правая','правое','правые','прав','right','rh'},
 'front':{'передній','передня','переднє','передні','передний','передняя','переднее','передние','перед','front'},
 'rear':{'задній','задня','заднє','задні','задний','задняя','заднее','задние','зад','rear'},
 'upper':{'верхній','верхня','верхнее','верхний','верхняя','upper'},
 'lower':{'нижній','нижня','нижний','нижняя','нижнее','lower'},
 'inner':{'внутрішній','внутрішня','внутренний','внутренняя','inner'},
 'outer':{'зовнішній','зовнішня','зовнішнє','наружный','наружная','наружное','outer'},
}
COSMETIC=set('чорний чорна чорне черный черная черное білий біла біле белый белая белое червоний червона красный красная сірий сіра серый серая синій синя синий синяя бежевий бежевый срібний серебристый used бу'.split())
COSMETIC.update('подряпини подряпина царапины царапина пісок песок сколи сколы відколи вмятины іржавий іржава ржавый ржавая потерта потертий потертый потёртый потертость павутинка павутина'.split())
TECH=set('full адаптив led ксенон xenon галоген halogen адаптивна адаптивний адаптивная adaptive'.split())

def surface(source):
    title=source.get('title','');text=unicodedata.normalize('NFKC',title).casefold()
    for abbreviation,word in [('л.','ліва'),('пр.','права'),('пер.','передня'),('зад.','задня')]:
        text=re.sub(r'(?<!\w)'+re.escape(abbreviation)+r'(?=\W|$)',word,text)
    text=re.sub(r'\bб\s*/\s*[ву]\b',' ',text)
    removed=[];features={};cosmetic_phrases=[]
    model_words={source.get('model','').casefold()}-set([''])
    if norm(source.get('manufacturer',''))=='volvo':model_words.update('xc40 xc60 xc90 s60 s90 v40 v60 v90 c30 c40 ex30 ex90'.split())
    title_models=sorted({m for m in model_words if re.search(r'(?<!\w)'+re.escape(m)+r'(?!\w)',text)})
    year_labels=[]
    for m in title_models:
        pattern=r'(?<!\w)'+re.escape(m)+r'\s+(\d{2}\s*[-–]\s*\d{2})(?!\w)'
        year_labels.extend(re.findall(pattern,text));text=re.sub(pattern,m,text)
    features['title_models']=title_models
    features['title_year_labels']=sorted(set(year_labels+re.findall(r'\b(?:19|20)\d\d(?:\s*[-–]\s*(?:19|20)\d\d)?\b',text)))
    def extract(pattern,key):
        nonlocal text
        found=re.findall(pattern,text)
        if found:features[key]=sorted(set(found));text=re.sub(pattern,' ',text)
    extract(r'\b([tbd][1-9])\b','engine_labels')
    extract(r'\b([1-6][.,]\d(?:\s*(?:d|t|tdi|tfsi))?)\b','displacement_labels')
    extract(r'\b(?:код|code)\s*:\s*([a-z0-9][a-z0-9-]{1,19})\b','modification_codes')
    extract(r'\bтип\s+([0-9]{1,2})\b','construction_type')
    extract(r'\b([0-9]{1,4}\s*(?:kw|квт|w|a|а|v|в))\b','ratings')
    material={'алюміній':'aluminium','алюминий':'aluminium','aluminium':'aluminium','сталь':'steel'}
    materials=sorted({v for k,v in material.items() if re.search(r'\b'+k+r'\b',text)})
    if materials:features['material']=materials
    for token in material:text=re.sub(r'\b'+token+r'\b',' ',text)
    for phrase,value in [('у зборі','complete'),('в зборі','complete'),('в сборе','complete'),('голий','bare'),('голый','bare')]:
        if re.search(r'\b'+phrase+r'\b',text):features.setdefault('assembly',[]).append(value);text=re.sub(r'\b'+phrase+r'\b',' ',text)
    for phrase in ('під полірування','под полировку','під поліроку','під чищення','под чистку','под химчистку','в клею','в клеї','в клее','выгорел лак','поліз лак'):
        if phrase in text:cosmetic_phrases.append(phrase);text=text.replace(phrase,' ')
    for color in COSMETIC:
        text=re.sub(r'\b'+re.escape(color)+r'\s+\d{3}\b',color,text)
    for field in ('oem','article','manufacturer','model'):
        value=source.get(field) or ''
        if not value:continue
        if field in ('oem','article') and len(re.sub(r'\W','',value))<5:continue
        pattern=r'(?<!\w)'+re.escape(unicodedata.normalize('NFKC',value).casefold())+r'(?!\w)'
        if re.search(pattern,text):removed.append({field:value});text=re.sub(pattern,' ',text)
    for model in title_models:text=re.sub(r'(?<!\w)'+re.escape(model)+r'(?!\w)',' ',text)
    text=re.sub(r'\b(?:18[89]\d|19\d\d|20\d\d|2100)\b',' ',text)
    text=norm(text)
    tokens=text.split();found={k for k,words in DIRECTIONS.items() if words.intersection(tokens)}
    for field in ('side','position'):
        found.update(k for k,words in DIRECTIONS.items() if words.intersection(norm(source.get(field,'')).split()))
    conflicts=[]
    for a,b in [('left','right'),('front','rear'),('upper','lower'),('inner','outer')]:
        if a in found and b in found:conflicts.append(a+'/'+b)
    direction_words=set().union(*DIRECTIONS.values())
    explicit=set(norm(source.get('side','')+' '+source.get('position','')).split())-direction_words
    if explicit:conflicts.append('unsupported explicit installation: '+' '.join(sorted(explicit)))
    tech_names={'ксенон':'xenon','галоген':'halogen','адаптивна':'adaptive','адаптивний':'adaptive','адаптивная':'adaptive','адаптив':'adaptive','full':'full'}
    features['technology']=sorted({tech_names.get(t,t) for t in set(tokens)&TECH})
    residue=' '.join(t for t in tokens if t not in direction_words|COSMETIC|TECH|{'oem','артикул','арт'})
    return dict(phrase=residue,side=next((k for k in ('left','right') if k in found),'unknown'),
        position=next((k for k in ('front','rear') if k in found),'unknown'),
        mount=sorted(found&{'upper','lower','inner','outer'}),features=features,conflicts=conflicts,
        removed=removed,cosmetic=sorted(set(tokens)&COSMETIC)+cosmetic_phrases,title_years=re.findall(r'\b(?:19|20)\d\d\b',title))

TYPES={}
LEX={}
for rule in RULES['types']:
    record=type_record(rule['name'],rule['category'],rule['subcategory']);TYPES[record['id']]=record
    for alias in rule['aliases']:
        phrase=surface({'title':alias})['phrase']
        if not any(r['type_id']==record['id'] for r in LEX.get(phrase,[])):
            LEX.setdefault(phrase,[]).append({**rule,'type_id':record['id']})


def classify(source,aliases=()):
    parsed=surface(source)
    evidence={'normalization':parsed,'rule_version':RULES['version'],'source':source}
    candidate=[]
    # New owner aliases are exact full-phrase/context or exact immutable source.
    for alias in aliases:
        c=alias['criteria']
        match=(c.get('source_key')==source['key'] and c.get('source_sha')==source['sha']) if c.get('source_key') else (
            norm(c.get('phrase',''))==parsed['phrase'] and all(not c.get(k) or norm(c[k])==norm(source.get(k,'')) for k in ('category','subcategory','manufacturer','model')))
        if match:candidate.append(alias)
    if any(a['criteria'].get('source_key') for a in candidate):candidate=[a for a in candidate if a['criteria'].get('source_key')]
    if candidate:evidence['alias_ids']=[a['id'] for a in candidate]
    if any(not a.get('enabled',True) for a in candidate):return dict(quality='review',reason='Owner requested review',evidence=evidence)
    targets={digest([a['type_id'],a['criteria'].get('installation')]) for a in candidate}
    if len(targets)>1:return dict(quality='review',reason='Conflicting verified aliases',evidence=evidence)
    if candidate:
        chosen=sorted(candidate,key=lambda a:a['id'])[0];c=chosen['criteria'];override=c.get('installation')
        if parsed['conflicts'] and not override:return dict(quality='review',reason='Conflicting installation facts',evidence=evidence)
        installation=override or {k:parsed[k] for k in ('side','position','mount')}
        evidence['alias_ids']=[a['id'] for a in candidate]
        return dict(quality='verified_owner',type_id=chosen['type_id'],installation=installation,features={**parsed['features'],'owner_reviewed_descriptor':parsed['phrase']},evidence=evidence)
    if not parsed['phrase']:return dict(quality='unprocessed',reason='No functional name',evidence=evidence)
    rules=LEX.get(parsed['phrase'],[])
    if len(rules)!=1:return dict(quality='review' if rules else 'unprocessed',reason='No unique exact functional rule',evidence=evidence)
    rule=rules[0];category=CATEGORY_ALIASES.get(source.get('category',''),source.get('category',''))
    if norm(category) not in {norm(c) for c in rule['categories']}:
        return dict(quality='review',reason='Function/context disagreement',evidence=evidence)
    position=parsed['position']
    if parsed['conflicts'] or (rule.get('require_assembly') and rule['require_assembly'] not in parsed['features'].get('assembly',[])) or (rule.get('require_mount') and rule['require_mount'] not in parsed['mount']) or (rule.get('require_side') and parsed['side']=='unknown') or (
        rule.get('require_position') and position=='unknown') or (rule.get('require_rear_word') and position!='rear') or (
        rule.get('forbidden_position')==position):
        return dict(quality='review',reason='Installation is missing or contradictory',evidence=evidence)
    position=rule.get('default_position','unknown') if position=='unknown' else position
    return dict(quality='verified_rule',type_id=rule['type_id'],installation={'side':parsed['side'],'position':position,'mount':parsed['mount']},features=parsed['features'],evidence=evidence)


def placement(result):
    p=result['installation'];details={'mount':sorted(p.get('mount',[]))};key=digest([result['type_id'],p['side'],p['position'],details])
    return dict(id=sid('placement',key),identity_key=key,type_id=result['type_id'],side=p['side'],position=p['position'],details=details)


def variant(source,result,place):
    # Opaque OEM string retained; no splitting, substring or cross-model union.
    oem=unicodedata.normalize('NFKC',source.get('oem') or '').strip() or None
    attrs={k:source.get(k) or '' for k in ('manufacturer','model','generation','year_from','year_to','engine','fuel_type','transmission')}
    attrs['features']=result['features'];attrs['interchangeability']='unverified'
    if not oem:attrs['unknown_oem_source']=[source.get('provider'),source.get('article') or source['key']]
    return dict(id=sid('variant',result['type_id'],place['id'],oem,attrs),type_id=result['type_id'],placement_id=place['id'],oem=oem,attributes=attrs)

# Pin executable normalization as well as vocabulary; old publications are never
# silently reinterpreted after a parser/Unicode change.
from hashlib import sha256
RULE_FINGERPRINT=digest([RULES,sha256(Path(__file__).read_bytes()).hexdigest(),unicodedata.unidata_version])
