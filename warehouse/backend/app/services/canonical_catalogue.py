"""Explicit v3 normalization publications; old catalogue/stock tables are read-only."""
from collections import Counter
from sqlalchemy import select,text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased
from fastapi import HTTPException
from app.models.catalogue import CataloguePath as Path,CatalogueOffer as Offer,CatalogueEntity as Entity,CatalogueSource as Source,CatalogueState as V2State
from app.models.canonical import CanonicalType as Type,CanonicalPlacement as Placement,CanonicalVariant as Variant,CanonicalAlias as Alias,CanonicalMapping as Mapping,CanonicalState as State,CanonicalRun as Run
from app.services.catalogue_import import LOCK
from app.services.catalogue_format import digest
from app.services.canonical_rules import BASE,RULES,RULE_FINGERPRINT,TYPES,classify,placement,variant,sid,norm,UNIVERSAL,UNIVERSAL_TYPES


def source_record(**row):return {**row,'sha':digest(row)}

def base_inputs():
    return [source_record(key='base:'+BASE['version']+':'+key,kind='base',title=name,category=c['name'],subcategory=s['name'],
        side='',position=position,manufacturer='',model='',generation='',oem=None,article='',provider=BASE['version'],
        legacy_ref={'source':BASE['version'],'catalog_key':key},year_from=None,year_to=None)
        for c in BASE['categories'] for s in c['subcategories'] for key,name,position in s['parts']]


def constructive_inputs():
    # Original 33 sources/keys are immutable. Avoid adding a broad duplicate of
    # any function already represented by that baseline.
    represented={classify(source).get('type_id') for source in base_inputs()}
    return [source_record(key='base:'+UNIVERSAL['version']+':'+tid,kind='base',constructive_type_id=tid,
        title=r['name'],category=r['category'],subcategory=r['subcategory'],side='',position='',manufacturer='',model='',generation='',oem=None,article='',provider=UNIVERSAL['version'],year_from=None,year_to=None)
        for tid,r in UNIVERSAL_TYPES.items() if tid not in represented]


def global_inputs(db,model_ids=None):
    model,brand=aliased(Entity),aliased(Entity)
    stmt=select(Path,Offer,model,brand,Source).join(Offer,Offer.id==Path.offer_id).join(model,model.id==Path.model_id).join(brand,brand.id==model.parent_id).join(Source,Source.id==Offer.source_id).order_by(Path.id)
    if model_ids is not None:stmt=stmt.where(Path.model_id.in_(model_ids))
    result=base_inputs()+constructive_inputs()
    for path,offer,m,b,provider in db.execute(stmt):
        r=path.raw;p=offer.properties
        result.append(source_record(key='v2:'+path.id,kind='v2',path_id=path.id,offer_id=offer.id,model_id=m.id,
            provider=provider.name,article=offer.source_article,source_url=p['source_url'],title=p['part_name'],oem=p.get('oem'),
            category=r['category'],subcategory=r['subcategory'],manufacturer=b.name,model=m.name,
            generation=r.get('generation') or m.details.get('generation',''),year_from=r.get('year_from'),year_to=r.get('year_to'),
            side=r.get('side',''),position=r.get('position',''),raw=r))
    return result


def latest_aliases(db):
    rows=db.scalars(select(Alias).distinct(Alias.series_key).order_by(Alias.series_key,Alias.revision.desc()))
    return [dict(id=a.id,type_id=a.type_id,criteria=a.criteria,enabled=a.enabled) for a in rows]


def analyze(db):
    sources=global_inputs(db);aliases=latest_aliases(db)
    types={**TYPES,**{t.id:{c.name:getattr(t,c.name) for c in Type.__table__.columns} for t in db.scalars(select(Type))}}
    rev=db.get(V2State,1)
    sha=digest([RULE_FINGERPRINT,BASE,[(r['key'],r['sha']) for r in sources],aliases,sorted(types),rev.revision if rev else None])
    placements={};variants={};mappings=[];counts=Counter();offer_results={};issues=[]
    for source in sources:
        outcome=classify(source,aliases);quality=outcome['quality'];counts[quality]+=1
        record=dict(id=sid('mapping',sha,source['key']),snapshot_sha=sha,source_kind=source['kind'],source_key=source['key'],
            source_sha=source['sha'],catalogue_path_id=source.get('path_id'),type_id=None,placement_id=None,variant_id=None,
            quality=quality,evidence={**outcome['evidence'],'reason':outcome.get('reason')})
        if quality.startswith('verified'):
            record['evidence']['resolved_installation']=outcome['installation']
            record['evidence']['resolved_features']=outcome['features']
            record['type_id']=outcome['type_id'];p=placement(outcome);placements[p['id']]=p;record['placement_id']=p['id']
            if source['kind']!='base':
                v=variant(source,outcome,p);variants[v['id']]=v;record['variant_id']=v['id']
        else:
            if len(issues)<200:issues.append(dict(source_key=source['key'],source_sha=source['sha'],title=source['title'],
                phrase=outcome['evidence']['normalization']['phrase'],category=source['category'],subcategory=source['subcategory'],
                reason=outcome['reason'],quality=quality))
        if source['kind']=='v2':offer_results.setdefault(source['offer_id'],[]).append(quality.startswith('verified'))
        mappings.append(record)
    mapped=sum(any(values) for values in offer_results.values());total=len(offer_results)
    used_types={m['type_id'] for m in mappings if m['type_id']}
    report=dict(alias_revision_ids=[a['id'] for a in aliases],snapshot_sha=sha,rule_version=RULES['version'],universal_version=UNIVERSAL['version'],rules_sha=RULE_FINGERPRINT,input_records=len(sources),base_positions=len(base_inputs()),constructive_positions=len(constructive_inputs()),
        source_offers=total,canonical_types=len(used_types),variants=len(variants),placements=len(placements),
        confirmed_mappings=counts['verified_rule']+counts['verified_owner'],ambiguous_mappings=counts['review'],
        unprocessed_records=counts['unprocessed'],mapped_offers=mapped,fully_mapped_offers=sum(all(v) for v in offer_results.values()),
        trusted_offer_fraction=mapped/total if total else None,issues=issues,issues_truncated=counts['review']+counts['unprocessed']>len(issues),
        committed=False,fitment_inferred=False)
    token=digest([sha,report])
    return dict(policy={'rules_sha':RULE_FINGERPRINT,'alias_ids':[a['id'] for a in aliases]},types=[types[t] for t in sorted(used_types)],placements=list(placements.values()),variants=list(variants.values()),mappings=mappings,report=report,token=token,snapshot_sha=sha)


def build(db,publish=False,preview_id=None,token=None):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
    plan=analyze(db)
    if publish:
        previous=db.get(Run,preview_id)
        if not previous or previous.mode!='preview' or previous.status!='done' or token!=previous.token or token!=plan['token']:
            raise HTTPException(409,'Джерела або правила змінилися; потрібна нова перевірка нормалізації')
        for cls,rows in [(Type,plan['types']),(Placement,plan['placements']),(Variant,plan['variants']),(Mapping,plan['mappings'])]:
            for start in range(0,len(rows),500):
                db.execute(insert(cls).values(rows[start:start+500]).on_conflict_do_nothing(index_elements=['id']))
        state=db.get(State,1)
        if not state:raise HTTPException(503,'Міграцію canonical state не застосовано')
        state.snapshot_sha=plan['snapshot_sha'];state.policy=plan['policy']
        plan['report']={**plan['report'],'committed':True}
    return plan
