"""Read-only candidates; no DismantlingItem/Part creation, exclusion or pricing."""
from collections import defaultdict
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import aliased
from app.models import Category,DismantlingCatalogType as LocalType,DismantlingCatalogSource as LocalSource
from app.models.catalogue import CatalogueEntity as Entity,CataloguePrice as Price
from app.models.aleto import AletoModel,AletoOffer,AletoTaxonomy,AletoPrice
from app.models.canonical import CanonicalState as State,CanonicalType as Type,CanonicalMapping as Mapping,CanonicalAlias as Alias,CanonicalFitment as Fitment
from app.services.aleto_import import identity
from app.services.canonical_rules import RULES,RULE_FINGERPRINT,classify,placement,variant,norm
from app.services.catalogue_format import digest
from app.services.canonical_catalogue import global_inputs,source_record


def legacy_inputs(db,workspace,query):
    result=[]
    for item,src in db.execute(select(LocalType,LocalSource).join(LocalSource,LocalSource.id==LocalType.source_id).where(LocalType.account_id==workspace,LocalSource.account_id==workspace)):
        result.append(source_record(kind='local',key='local:'+src.id+':'+item.catalog_key,title=item.name,category=item.category_name,subcategory=item.subcategory_name,
            side='',position=item.position,oem=None,manufacturer='',model='',generation='',year_from=None,year_to=None,provider='local',article='',
            legacy_ref={'source':'local.'+src.id,'catalog_key':item.catalog_key}))
    root,sub=aliased(Category),aliased(Category)
    stmt=select(AletoTaxonomy,AletoOffer,AletoModel,root,sub).join(AletoOffer,(AletoOffer.id==AletoTaxonomy.offer_id)&(AletoOffer.account_id==workspace)).join(AletoModel,(AletoModel.id==AletoTaxonomy.model_id)&(AletoModel.account_id==workspace)).join(root,(root.id==AletoTaxonomy.category_id)&(root.account_id==workspace)).outerjoin(sub,(sub.id==AletoTaxonomy.subcategory_id)&(sub.account_id==workspace)).where(AletoTaxonomy.account_id==workspace,root.archived.is_(False))
    for path,offer,model,c,s in db.execute(stmt):
        if identity(model.manufacturer)!=identity(query['manufacturer']) or identity(model.model)!=identity(query['model']):continue
        if s and s.archived:continue
        result.append(source_record(kind='v1',key='v1:'+path.id,title=offer.title,oem=offer.oem,category=c.name,subcategory=s.name if s else path.raw_subcategory,
            side='',position='',manufacturer=model.manufacturer,model=model.model,generation='',year_from=None,year_to=None,
            provider=offer.source,article=offer.source_article,source_url=offer.source_url,offer_id=offer.id,legacy_ref={'source':'aleto.v1','taxonomy_id':path.id,'offer_id':offer.id}))
    return result


def compatibility(source,query,assertions,features=None):
    matches=[]
    # Latest statement for the identical criteria preserves corrections, not old
    # conflicting history. Overlapping distinct contradictory statements review.
    latest={}
    for assertion in sorted(assertions,key=lambda a:(a.created_at,a.id)):latest[digest(assertion.criteria)]=assertion
    for a in latest.values():
        c=a.criteria
        if any(identity(c[k])!=identity(query[k]) for k in ('manufacturer','model')):continue
        if query.get('year') is not None:
            if c.get('year_from') is None or c.get('year_to') is None or not c['year_from']<=query['year']<=c['year_to']:continue
        if any(query.get(k) and (not c.get(k) or identity(query[k])!=identity(c[k])) for k in ('generation','engine','fuel_type','transmission')):continue
        # Criteria that need facts absent from the vehicle cannot confirm fitment.
        if any(c.get(k) and not query.get(k) for k in ('generation','engine','fuel_type','transmission')):continue
        if query.get('year') is None and (c.get('year_from') is not None or c.get('year_to') is not None):continue
        matches.append(a)
    statuses={a.status for a in matches}
    if len(statuses)>1:return {'status':'unknown','reason':'Conflicting owner fitment evidence','evidence_ids':[a.id for a in matches]}
    if statuses:return {'status':next(iter(statuses)),'reason':'Explicit owner-reviewed fitment evidence','evidence_ids':[a.id for a in matches]}
    features=features or {}
    title_models=features.get('title_models',[])
    same_model=bool(source.get('model')) and identity(source['manufacturer'])==identity(query['manufacturer']) and identity(source['model'])==identity(query['model'])
    if title_models and source.get('model','').casefold() not in title_models:same_model=False
    if source.get('generation') and query.get('generation') and identity(source['generation'])!=identity(query['generation']):same_model=False
    return {'status':'possible' if same_model else 'unknown','reason':'Source model grouping only; year, engine and equipment not verified' if same_model else 'No verified vehicle fitment evidence','evidence_ids':[]}


def candidates(db,query,workspace=None,offset=0,limit=100):
    state=db.get(State,1)
    if not state or not state.snapshot_sha:return {'items':[],'total':0,'unmapped':[],'unmapped_total':0,'published':False,'read_only':True}
    if state.policy.get('rules_sha')!=RULE_FINGERPRINT:raise HTTPException(409,'Версію правил змінено; власник має опублікувати нову нормалізацію')
    brand=aliased(Entity)
    models=list(db.scalars(select(Entity).join(brand,brand.id==Entity.parent_id).where(Entity.kind=='model',Entity.normalized_name==identity(query['model']),brand.normalized_name==identity(query['manufacturer']))))
    sources=global_inputs(db,[m.id for m in models])
    aliases=[dict(id=a.id,type_id=a.type_id,criteria=a.criteria,enabled=a.enabled) for a in db.scalars(select(Alias).where(Alias.id.in_(state.policy.get('alias_ids',[]))))]
    mapping={m.source_key:m for m in db.scalars(select(Mapping).where(Mapping.snapshot_sha==state.snapshot_sha))}
    types={t.id:t for t in db.scalars(select(Type))}
    if workspace:sources+=legacy_inputs(db,workspace,query)
    v2_ids={s['offer_id'] for s in sources if s['kind']=='v2'};v1_ids={s['offer_id'] for s in sources if s['kind']=='v1'}
    observations=defaultdict(list)
    for cls,kind,ids in [(Price,'v2',v2_ids),(AletoPrice,'v1',v1_ids)]:
        keys=list(ids)
        for start in range(0,len(keys),500):
            stmt=select(cls).where(cls.offer_id.in_(keys[start:start+500]))
            if kind=='v1':stmt=stmt.where(cls.account_id==workspace)
            for p in db.scalars(stmt):observations[(kind,p.offer_id)].append(p)
    assertions=defaultdict(list)
    for a in db.scalars(select(Fitment)):assertions[a.variant_id].append(a)
    groups={};unmapped=[]
    for source in sources:
        if source['kind'] in ('base','v2'):
            row=mapping.get(source['key'])
            if not row or row.source_sha!=source['sha']:
                unmapped.append({'source_key':source['key'],'reason':'Source is new or changed since publication'});continue
            if not row.type_id:
                unmapped.append({'source_key':source['key'],'reason':row.evidence.get('reason'),'quality':row.quality});continue
            outcome=dict(type_id=row.type_id,quality=row.quality,installation=row.evidence['normalization'],features=row.evidence['normalization']['features'])
            # Owner-approved installation overrides are recorded separately.
            outcome['installation']=row.evidence.get('resolved_installation',outcome['installation'])
            outcome['features']=row.evidence.get('resolved_features',outcome['features'])
        else:outcome=classify(source,aliases)
        if not outcome.get('type_id') or outcome['type_id'] not in types:
            unmapped.append({'source_key':source['key'],'reason':outcome.get('reason','Type not published')});continue
        p=placement(outcome);t=types[outcome['type_id']]
        group=groups.setdefault(p['id'],dict(canonical_type_id=t.id,name=t.name,category=t.category,subcategory=t.subcategory,
            placement=p,variants={},source_refs=[],qualities=set(),offer_keys=set(),observations={},compatibilities=[]))
        group['qualities'].add(outcome['quality']);group['source_refs'].append({'kind':source['kind'],'key':source['key'],'legacy_ref':source.get('legacy_ref'),
            'provider':source.get('provider'),'article':source.get('article'),'offer_id':source.get('offer_id'),'source_url':source.get('source_url')})
        if source['kind'] not in ('base','local'):
            v=variant(source,outcome,p);v['compatibility']=compatibility(source,query,assertions[v['id']],outcome['features'])
            group['variants'][v['id']]=v;group['offer_keys'].add((source['provider'],source['article']))
            group['compatibilities'].append(v['compatibility'])
            for obs in observations.get((source['kind'],source.get('offer_id')),[]):group['observations'][(source['kind'],obs.id)]=obs
    result=[]
    for group in groups.values():
        prices={}
        for currency,field in [('UAH','price_uah'),('USD','price_usd')]:
            values=[getattr(p,field) for p in group['observations'].values() if getattr(p,field) is not None]
            prices[currency]={'min':str(min(values)) if values else None,'max':str(max(values)) if values else None,'observation_count':len(values),
                'latest_observed_at':max((p.observed_at for p in group['observations'].values() if getattr(p,field) is not None),default=None)}
        fits=group.pop('compatibilities');statuses={v['status'] for v in fits}
        status='confirmed' if 'confirmed' in statuses else 'possible' if 'possible' in statuses else 'unknown'
        if statuses=={'incompatible'}:status='incompatible'
        result.append({**{k:v for k,v in group.items() if k not in ('observations','offer_keys','qualities','variants','source_refs')},
            'variants':list(group['variants'].values()),'offer_count':len(group['offer_keys']),'quality':sorted(group['qualities']),
            'compatibility':status,'compatibility_scope':'at_least_one_variant','fitment_note':'Variant-level evidence applies only to the stated criteria; no equipment inference',
            'reference_prices':prices,'source_refs':group['source_refs'][:50],'source_ref_count':len(group['source_refs']),
            'source_refs_truncated':len(group['source_refs'])>50,'selling_price':None})
    result.sort(key=lambda r:(r['category'],r['subcategory'],r['name'],r['placement']['id']))
    return {'items':result[offset:offset+limit],'total':len(result),'unmapped':unmapped[:50],'unmapped_total':len(unmapped),
        'snapshot_sha':state.snapshot_sha,'published':True,'read_only':True}
