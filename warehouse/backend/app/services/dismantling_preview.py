"""Stateless configuration-aware preview; this module never writes database rows."""
from fastapi import HTTPException
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
from statistics import median
from sqlalchemy import select
from app.models.catalogue import CatalogueOffer,CataloguePrice
from app.models.canonical import CanonicalFitment
from app.services.canonical_rules import surface
from app.services.canonical_candidates import candidates
from app.services.canonical_applicability import assess
from app.services.vehicle_configuration import latest,resolve,baseline

VERSION='carpot.dismantling.preview.2a.1'
PRICE_VERSION='carpot.comparable-prices.1'
RULES=[dict(id=key,version=VERSION,source=source,explanation=explanation) for key,source,explanation in [
 ('constructive-function','canonical_rules_v1_5.json','Глобальна функція є кандидатом, а не доказом встановлення'),
 ('powertrain-constraints','canonical_rules_v1_5.json applicability','Підтверджений несумісний тип силової установки позначає кандидата, не видаляючи його'),
 ('source-constraints','immutable canonical mapping evidence','Явні паливні, приводні та опційні ознаки зберігаються окремо від фактичної комплектації'),
 ('missing-or-conflicting','VehicleConfiguration provenance/confidence','Невідомі або суперечливі дані не означають відсутність деталі'),
 ('explicit-fitment','append-only canonical_fitments','Confirmed вимагає підтвердженої конфігурації та явного доказу, який охоплює всі відомі критерії')]]

def utcnow():return datetime.now(timezone.utc)

def configuration(db,vehicle,workspace,facts,selected):
    saved=latest(db,vehicle,workspace)
    if not facts and not selected and saved and saved['status']=='confirmed':
        current=baseline(vehicle);conflicts=list(saved['conflicts'])
        from app.services.vin_normalize import ukrainian,drive_code
        for field in ('powertrain','drive','engine_code','body_type'):
            a=current.get(field);b=saved['values'].get(field)
            if a is None or b is None:continue
            if field=='body_type':a=ukrainian('body_class',a);b=ukrainian('body_class',b)
            if field=='drive':a=drive_code(a);b=drive_code(b)
            if str(a).casefold()!=str(b).casefold():conflicts.append(dict(field=field,reason='Збережене підтвердження суперечить поточним VIN/Vehicle характеристикам'))
        return {**saved,'conflicts':conflicts,'reviewed':not conflicts}

    # Reuse the existing resolver without persisting a configuration preview.
    prior=[]
    if saved and saved['status']=='confirmed':
        for field,p in saved['provenance'].items():
            if field in ('engine_label',) or saved['values'].get(field) is None:continue
            prior.append(dict(field=field,value=saved['values'][field],kind=p['kind'] if p['kind'] in ('manual','document','vin_decode') else 'manual',reference=p['reference'],confidence=p['confidence']))
    # Ephemeral overrides supersede a field only for this request, retain provenance.
    fields={f['field'] for f in facts};prior=[f for f in prior if f['field'] not in fields]
    result=resolve(vehicle,prior+facts,{k:v+len(prior) for k,v in selected.items()})
    return {**result,'reviewed':False,'persisted':False,'saved_configuration_status':saved['status'] if saved else None}

def price_summaries(db,variants,now):
    """Separate comparable variant/condition/currency cohorts; latest per offer only."""
    ids={s['offer_id'] for v in variants for s in v.get('_sources',[]) if s['kind']=='v2'}
    offers={};observations=defaultdict(list)
    keys=sorted(ids)
    for start in range(0,len(keys),500):
        for o in db.scalars(select(CatalogueOffer).where(CatalogueOffer.id.in_(keys[start:start+500]))):offers[o.id]=o
        for p in db.scalars(select(CataloguePrice).where(CataloguePrice.offer_id.in_(keys[start:start+500]),CataloguePrice.observed_at<=now,CataloguePrice.observed_at>=now-timedelta(days=90))):observations[p.offer_id].append(p)
    result=[]
    for variant in variants:
        if not variant.get('oem'):continue
        cohorts=defaultdict(dict)
        for source in variant.get('_sources',[]):
            offer=offers.get(source.get('offer_id'))
            if not offer:continue
            condition=str(offer.properties.get('condition') or '').strip().casefold()
            if not condition:continue
            rows=observations.get(offer.id,[])
            if not rows:continue
            latest_row=max(rows,key=lambda p:(p.observed_at,p.id))
            for currency,field in [('UAH','price_uah'),('USD','price_usd')]:
                value=getattr(latest_row,field)
                if value is not None and value>0:cohorts[(condition,tuple(surface({'title':offer.properties.get('part_name','')})['cosmetic']),currency)][offer.id]=(value,latest_row.observed_at)
        for (condition,cosmetic,currency),rows in sorted(cohorts.items()):
            if len(rows)<3:continue
            values=[v for v,_ in rows.values()]
            result.append(dict(variant_id=variant['id'],oem=variant['oem'],condition=condition,condition_details=list(cosmetic),currency=currency,offer_count=len(rows),minimum=str(min(values)),maximum=str(max(values)),median=str(median(values)),observed_at=max(t for _,t in rows.values()),label='Ринковий орієнтир',rule_version=PRICE_VERSION))
    return result

def status_for(variant,assessment,config):
    controlled=assessment.get('controlled_result')
    if controlled and controlled['status'] in ('confirmed','incompatible') and not config['conflicts']:return controlled['status'],'Явне опубліковане правило та перевірені характеристики; не доказ фізичної наявності'
    fit=variant.get('compatibility',{})
    # A partial/manual trial or contradictory facts cannot confirm or reject fitment.
    if config['conflicts']:return 'unknown','Конфліктні характеристики; уточніть джерело даних'
    if fit.get('status')=='unknown' and len(fit.get('evidence_ids',[]))>1:return 'unknown','Суперечливі докази сумісності; потрібен перегляд власника'
    known=config['values'];quality=config['provenance']
    verified=lambda k:quality.get(k,{}).get('confidence')=='verified'
    conflicts=assessment['conflicting_fields']
    if conflicts and all(verified(k) for k in conflicts):return 'incompatible','Підтверджені характеристики суперечать явним обмеженням варіанта/версійного правила'
    fields=[k for k,v in known.items() if v not in (None,'',[],False) and k not in ('vin','engine_label','options_complete')]
    if config['reviewed'] and (not known.get('engine_label') or known.get('engine_code')) and all(verified(k) for k in fields) and fit.get('status') in ('confirmed','incompatible'):
        return fit['status'],'Явний переглянутий доказ fitment охоплює відому конфігурацію'
    if assessment['missing_or_unverified'] or 'E' in assessment['groups']:return 'unknown','Недостатньо підтверджених даних; позицію не виключено'
    return 'possible','Конструктивна функція/джерельна модель є кандидатом; точний fitment не підтверджено'

def preview(db,vehicle,workspace,facts=(),selected=None,now=None,*,universal_base=False):
    config=configuration(db,vehicle,workspace,list(facts),selected or {})
    values=config['values'];query={k:values.get(k) or '' for k in ('manufacturer','model','generation','fuel_type','transmission','powertrain','drive','body_type','engine_code','options')}
    query['year']=values.get('year');query['engine']=values.get('engine_code') or values.get('engine_label') or ''
    gaps=[]
    try:page=candidates(db,query,workspace,0,1000000,configuration=config,include_rule_sources=True)
    except HTTPException as e:
        if not universal_base or e.status_code!=409:raise
        gaps.append('Опублікована нормалізація потребує оновлення; використано доступні довідкові типи.')
        page=dict(items=[],unmapped_total=0,published=False,snapshot_sha=None)
    rows=page['items'];unmapped=page['unmapped_total'];snapshot=page.get('snapshot_sha');published=page['published']
    exact=[];baseline_added=0;reference_added=0
    if universal_base:
        from app.services.universal_generator import exact_modification_rows,published_reference_rows
        exact,source_gaps=exact_modification_rows(vehicle,config,db);gaps.extend(source_gaps)
        if exact:rows=exact
        else:
            references=published_reference_rows(db,config);known={r['placement']['id'] for r in rows}
            for row in references:
                if row['placement']['id'] not in known:rows.append(row);known.add(row['placement']['id']);reference_added+=1
    if not exact and (not published or universal_base):
        from app.services.canonical_catalogue import base_inputs,constructive_inputs
        from app.services.canonical_rules import classify,placement,TYPES
        baseline_excluded_types={r['canonical_type_id'] for r in rows}
        for source in base_inputs()+(constructive_inputs() if universal_base else []):
            outcome=classify(source)
            if not outcome.get('type_id'):continue
            t=TYPES[outcome['type_id']]
            if universal_base and t['id'] in baseline_excluded_types:continue
            baseline_added+=1
            rows.append(dict(canonical_type_id=t['id'],name=t['name'],category=t['category'],subcategory=t['subcategory'],placement=placement(outcome),variants=[],source_refs=[{'kind':'base','key':source['key']}],source_ref_count=1,offer_count=0,applicability=assess(t['id'],query,configuration=values,provenance=config['provenance'])))
    # Model-scoped account catalogue is a separate candidate source.  It is not
    # published canonical evidence, fitment verification, or an inventory receipt.
    # Distinct stable identities keep unknown names from being guessed as OEMs.
    from app.services.dismantling_catalog import scoped_types
    from app.services.canonical_rules import sid
    for local,src in scoped_types(db,workspace,vehicle):
        type_id=sid('local-scoped-type',src.id,local.catalog_key)
        placement_id=sid('local-scoped-placement',src.id,local.catalog_key)
        install=dict(id=placement_id,type_id=type_id,side='unknown',position='unknown',
                     details={'mount':[]},identity_key=placement_id)
        rows.append(dict(canonical_type_id=type_id,name=local.name,
                         category=local.category_name,subcategory=local.subcategory_name,
                         placement=install,variants=[],
                         source_refs=[dict(kind='local',key='local:'+src.id+':'+local.catalog_key,
                                           legacy_ref={'source':'local.'+src.id,'catalog_key':local.catalog_key})],
                         source_ref_count=1,offer_count=0,
                         applicability=assess(type_id,query,configuration=values,
                                              provenance=config['provenance'])))
    rows=list({r['placement']['id']:r for r in rows}.values())
    if universal_base:
        from app.services.catalogue_carpot_sections import propose_section,propose_subcategory
        for row in rows:
            if row.get('source_confirmed'):continue
            section=propose_section(row['category'],row['subcategory'],row['name'])['section']
            subsection=propose_subcategory(section,row['category'],row['subcategory'],row['name'])['subcategory']
            row['category']=section or 'Потребує уточнення';row['subcategory']=subsection or 'Потребує уточнення'
        gaps.append('Повнота універсального PRD і заводська комплектація не підтверджені; це доступні типи, не OEM/BOM.')
    prices_by_variant=defaultdict(list)
    for summary in price_summaries(db,[v for g in rows for v in g['variants']],now or utcnow()):prices_by_variant[summary['variant_id']].append(summary)
    evidence_ids={e for g in rows for v in g['variants'] for e in v.get('compatibility',{}).get('evidence_ids',[])}
    evidence_details={}
    keys=sorted(evidence_ids)
    for start in range(0,len(keys),500):
        for e in db.scalars(select(CanonicalFitment).where(CanonicalFitment.id.in_(keys[start:start+500]))):evidence_details[e.id]=dict(id=e.id,status=e.status,criteria=e.criteria,explanation=e.evidence,source='platform-owner-reviewed fitment',version=VERSION)
    items=[]
    for group in rows:
        variants=sorted(group['variants'],key=lambda v:v['id']);states=[]
        for v in variants:
            a=v['applicability'];state,explanation=status_for(v,a,config)
            v['applicability_status']=state;v['explanation']=explanation;states.append(state)
        a=group['applicability']
        status,explanation=status_for({},a,config)
        if states:
            status='confirmed' if 'confirmed' in states else 'possible' if 'possible' in states else 'unknown' if 'unknown' in states else 'incompatible'
            explanation='Оцінка на рівні варіантів; непідтверджені варіанти залишено видимими'
        prices=[p for v in variants if v['applicability_status']!='incompatible' for p in prices_by_variant[v['id']]]
        for v in variants:v.pop('_sources',None)
        items.append(dict(id=group['placement']['id'],canonical_part_type_id=group['canonical_type_id'],name=group['name'],installation_position=group['placement'],category=group['category'],subcategory=group['subcategory'],quantity=None,quantity_explanation='Конструктивно необхідна кількість не підтверджена; кількість оголошень не є кількістю деталей',variants=variants,source=sorted(group['source_refs'],key=lambda r:(r['kind'],r['key'])),source_confirmed=bool(group.get('source_confirmed')) and not config['conflicts'],source_ref_count=group['source_ref_count'],source_truncated=group.get('source_refs_truncated',False),rule_evidence={'version':VERSION,'source':'canonical_rules_v1_5.json','criteria':a,'vehicle_provenance':config['provenance']},applicability_status=status,explanation=explanation,applicability=a,compatible_evidence=sorted({e for v in variants for e in v.get('compatibility',{}).get('evidence_ids',[])}),evidence_details=[evidence_details[e] for e in sorted({e for v in variants for e in v.get('compatibility',{}).get('evidence_ids',[])}) if e in evidence_details],relevant_offer_count=group['offer_count'],reference_prices=prices,price_label='Ринковий орієнтир' if prices else 'Ціну не визначено',selling_price=None))
    items.sort(key=lambda i:(i['category'],i['subcategory'],i['name'],i['id']))
    counts=Counter(i['applicability_status'] for i in items)
    by_type=defaultdict(set)
    for i in items:by_type[i['canonical_part_type_id']].add(i['applicability_status'])
    type_counts=Counter(next(s for s in ('confirmed','possible','unknown','incompatible') if s in states) for states in by_type.values())
    unclassified={i['canonical_part_type_id'] for i in items if 'Потребує уточнення' in (i['category'],i['subcategory'])}
    if universal_base and unclassified:gaps.append(f'Категорія або підкатегорія потребує узгодження для {len(unclassified)} типів; записи не приховані.')
    generator=dict(uncategorized_types=len(unclassified),mode='universal',baseline_positions=baseline_added,published_reference_positions=reference_added,exact_source_positions=len(exact),gaps=gaps,categories=len({r['category'] for r in items if r['category']!='Потребує уточнення'}),types=len(by_type),positions=len(items),sources=sorted({r['kind'] for i in items for r in i['source']}),complete=False) if universal_base else None
    return dict(generator=generator,version=VERSION,read_only=True,persisted=False,configuration=config,items=items,total=len(items),unique_type_count=len(by_type),type_status_counts={s:type_counts[s] for s in ('confirmed','possible','unknown','incompatible')},status_counts={s:counts[s] for s in ('confirmed','possible','unknown','incompatible')},snapshot_sha=snapshot,published=published,fallback_used=not published,catalogue_status='published' if published else 'unpublished',unmapped_paths=unmapped,coverage_note='Нерозпізнані джерела збережені; відсутність зіставлення не означає непридатність',rules=RULES)
