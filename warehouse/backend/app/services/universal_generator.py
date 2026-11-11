"""Source adapters for the EXISTING managed plan. No queue, stock writes or paid API."""
from sqlalchemy import select
from app.models.canonical import CanonicalType,CanonicalPlacement
from app.services.canonical_rules import placement,sid
from app.services.canonical_applicability import assess
from app.services import unified_catalogue as catalogue


def explicit_rule(rules,config):
    """Only owner-published rules with verified, exact conditions can decide fitment."""
    effects=set();missing=set()
    for rule in rules:
        conditions=rule.get('when',{})
        if not conditions or not rule.get('evidence') or rule.get('effect') not in ('confirmed','incompatible'):continue
        different=False;unverified=[]
        for field,allowed in conditions.items():
            actual=config['values'].get(field)
            if not isinstance(allowed,list) or not allowed:unverified.append(field);continue
            if actual is None or config['provenance'].get(field,{}).get('confidence')!='verified':unverified.append(field)
            elif actual not in allowed:different=True
        if not different:
            missing.update(unverified)
            if not unverified:effects.add(rule['effect'])
    return dict(status=next(iter(effects)) if len(effects)==1 and not config['conflicts'] else 'unknown',missing=sorted(missing))


def published_reference_rows(db,config):
    result=[];types={};allowed={}
    for t in db.scalars(select(CanonicalType).order_by(CanonicalType.id)):
        metadata=t.provenance or {}
        if not metadata.get('universal_publication'):continue
        types[t.id]=t
        allowed[t.id]={placement(dict(type_id=t.id,installation={**p,'side':p.get('side','unknown'),'position':p.get('position','unknown'),'mount':p.get('mount',[]),'ordinal':[p['ordinal']] if p.get('ordinal') else []}))['id'] for p in metadata.get('declared_placements',[]) or [dict(side='unknown',position='unknown',mount=[])]}
    if not types:return result
    for p in db.scalars(select(CanonicalPlacement).where(CanonicalPlacement.type_id.in_(types)).order_by(CanonicalPlacement.type_id,CanonicalPlacement.id)):
        if p.id not in allowed[p.type_id]:continue
        t=types[p.type_id];metadata=t.provenance;path=metadata.get('corporate_path') or [t.category,t.subcategory]
        refs=[dict(kind='universal_prd',key=s['source_key']) for s in metadata.get('universal_sources',[]) if s.get('source_key')]
        if not refs:continue
        controlled=explicit_rule(metadata.get('fitment_rules',[]),config)
        result.append(dict(canonical_type_id=t.id,name=metadata.get('display_name_uk',t.name),category=path[0],subcategory=path[1],placement=dict(id=p.id,type_id=t.id,identity_key=p.identity_key,side=p.side,position=p.position,details=p.details),variants=[],source_refs=refs,source_ref_count=len(refs),offer_count=0,applicability=dict(groups=['E'],required_fields=[],missing_or_unverified=controlled['missing'],conflicting_fields=[],controlled_result=controlled)))
    return result


def exact_modification_rows(vehicle,config,db=None):
    """Exact pinned modification identity for ANY maker. Never match by display name."""
    selection=(vehicle.dismantling_v3 or {}).get('global_selection') or {}
    saved=catalogue.saved_state(vehicle)
    gaps=[]
    if not selection.get('car_id'):return [],['Немає точного каталожного зв’язку модифікації; використано доступні загальні типи.']
    if selection.get('vehicle_basis')!=catalogue.vehicle_basis(vehicle):return [],['Характеристики змінені після вибору модифікації; точний зв’язок потребує перевірки.']
    try:
        if saved:
            if saved.get('vehicle_basis')!=catalogue.vehicle_basis(vehicle):return [],['Збережений джерельний план потребує перевірки конфігурації.']
            payload=saved['payload']
        else:payload=catalogue.CatalogueAdapter().plan(selection['car_id'],global_source=True)['payload']
        catalogue.validate_plan(payload)
        if payload['car_id']!=selection['car_id'] or payload['model_id']!=selection['model_id'] or payload['manufacturer_id']!=selection['manufacturer_id'] or payload['source_snapshot_sha']!=selection['source_snapshot_sha']:
            return [],['Джерельний snapshot/модифікація змінилися; автоматичне змішування заблоковано.']
    except (catalogue.CatalogueUnavailable,KeyError,TypeError,ValueError):return [],['Точний глобальний каталог недоступний; дані не вигадано.']
    if payload['coverage']=='partial':gaps.append('Джерело має часткове покриття; це не повний заводський BOM.')
    bindings={}
    if db is not None:
        for t in db.scalars(select(CanonicalType)):
            for ref in (t.provenance or {}).get('universal_sources',[]):
                bindings.setdefault(ref['source_key'],[]).append(t)
    result=[]
    for row in payload['categories']:
        if row.get('kind')!='part' or payload.get('taxonomy_status')!='reviewed':continue
        source_key=f"td1q2018:prd:{row['product_id']}"
        candidates=bindings.get(source_key,[])
        matches=[t for t in candidates if any(ref['source_key']==source_key and ref.get('source_sha')==row.get('source_prd_sha256') for ref in t.provenance['universal_sources'])]
        if candidates and not matches:gaps.append('Контрольна сума PRD відсутня або змінилася; канонічне зіставлення потребує перевірки.')
        if len(matches)>1:
            gaps.append('Неоднозначний зв’язок PRD із канонічним типом; потрібен перегляд.');continue
        tid=matches[0].id if matches else sid('source-modification-type',str(payload['manufacturer_id']),str(row['product_id']))
        p=placement(dict(type_id=tid,installation={'side':'unknown','position':'unknown','mount':[]}))
        path=row['category_path'];key=f"car:{payload['car_id']}:product:{row['product_id']}"
        result.append(dict(canonical_type_id=tid,name=row['name_uk'],category=path[0],subcategory=path[1],placement=p,variants=[],source_refs=[dict(kind='global_modification',key=key,source_snapshot_sha=payload['source_snapshot_sha'],legacy_ref={'source':'carpot.catalogue.v1','catalog_key':key})],source_ref_count=1,offer_count=0,source_confirmed=True,applicability=assess(tid,{},configuration=config['values'],provenance=config['provenance'])))
    if len(result)<len(payload['categories']):gaps.append('Неузгоджені типи та витратні матеріали не видано за підтверджені фізичні деталі.')
    grouped={}
    for row in result:
        key=row['placement']['id']
        if key in grouped:
            grouped[key]['source_refs'].extend(row['source_refs'])
            grouped[key]['source_ref_count']=len(grouped[key]['source_refs'])
        else:grouped[key]=row
    return list(grouped.values()),gaps
