"""Bounded, read-only price projection. No inferred OEM or seller-price writes."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from statistics import median
import re,unicodedata
from urllib.parse import urlsplit
from fastapi import HTTPException
from sqlalchemy import select,or_,func,literal_column
from sqlalchemy.orm import aliased
from app.models import Part,Vehicle,DismantlingItem,Category
from app.models.catalogue import CatalogueOffer as Offer,CataloguePrice as Price,CataloguePath as Path,CatalogueEntity as Entity,CatalogueSource as Source,CatalogueState
from app.models.canonical import CanonicalState,CanonicalMapping as Mapping,CanonicalVariant as Variant,CanonicalPlacement as Placement,CanonicalAlias
from app.models.aleto import AletoOffer,AletoPrice,AletoTaxonomy,AletoModel
from app.services.canonical_rules import RULE_FINGERPRINT,classify,placement,surface
from app.services.canonical_applicability import assess
from app.services.catalogue_format import digest
from app.services.canonical_catalogue import source_record
VERSION='market-guidance.3c.1'
MAX_SOURCE_ROWS=20000
AGE_DAYS=90
CONDITIONS={'used':'used','б/у':'used','б/в':'used','вживана':'used','вживаний':'used','new':'new','нова':'new','новий':'new','damaged':'damaged','пошкоджена':'damaged','refurbished':'refurbished','відновлена':'refurbished'}
def utcnow():return datetime.now(timezone.utc)
def oem(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',value or '')).upper()
def identity(value):return ' '.join(unicodedata.normalize('NFKC',value or '').casefold().split())
def oem_sql(col):return func.upper(func.regexp_replace(func.normalize(col,literal_column('NFKC')),r'\s+','','g'))
def safe_url(value):
    try:
        u=urlsplit(value or '')
        return value if u.scheme=='https' and u.hostname and not u.username and not u.password else None
    except ValueError:return None

def parts_for(db,account,ids,lock=False):
    query=select(Part).where(Part.account_id==account,Part.id.in_(ids)).order_by(Part.id)
    if lock:query=query.with_for_update()
    rows=list(db.scalars(query))
    if len(rows)!=len(ids):raise HTTPException(404,'Деталь власного складу не знайдено')
    return rows

def latest_prices(db,cls,ids,now,account=None):
    result={};ids=sorted(ids)
    for start in range(0,len(ids),500):
        stmt=select(cls).where(cls.offer_id.in_(ids[start:start+500]),cls.observed_at<=now)
        if account is not None:stmt=stmt.where(cls.account_id==account)
        # Existing unique (offer_id, observed_at) index bounds latest-per-offer
        # projection. Historical observations never enter Python collections.
        for row in db.scalars(stmt.distinct(cls.offer_id).order_by(cls.offer_id,cls.observed_at.desc(),cls.id.desc())):result[row.offer_id]=row
    return result

def context(db,parts,account):
    vids={p.vehicle_id for p in parts if p.vehicle_id};ids=[p.id for p in parts]
    vehicles={v.id:v for v in db.scalars(select(Vehicle).where(Vehicle.account_id==account,Vehicle.id.in_(vids)))}
    links={d.part_id:d for d in db.scalars(select(DismantlingItem).where(DismantlingItem.account_id==account,DismantlingItem.part_id.in_(ids)))}
    placements={p.id:p for p in db.scalars(select(Placement).where(Placement.id.in_({p.canonical_placement_id for p in parts if p.canonical_placement_id})))}
    categories={c.id:c.name for c in db.scalars(select(Category).where(Category.account_id==account,Category.id.in_({i for p in parts for i in (p.category_id,p.subcategory_id) if i})))}
    result={}
    for p in parts:
        d=links.get(p.id);v=vehicles.get(p.vehicle_id)
        saved=(v.dismantling_v3 or {}).get('configuration') or {} if v else {}
        values={**({k:getattr(v,k) for k in ('manufacturer','model','generation','year','engine','fuel_type','transmission')} if v else {}),**saved.get('values',{})}
        if v and (v.dismantling_v3 or {}).get('vehicle_basis'):
            from app.services.vehicle_configuration import basis
            if v.dismantling_v3['vehicle_basis']!=basis(v):
                values={k:getattr(v,k) for k in ('manufacturer','model','generation','year','engine','fuel_type','transmission')}
                saved={} # stale equipment evidence cannot verify the changed donor
        snap=d.plan_v3.get('snapshot',{}) if d else {};pl=snap.get('installation_position')
        stored=placements.get(p.canonical_placement_id)
        if not pl and stored:pl={k:getattr(stored,k) for k in ('id','type_id','side','position','details')}
        tid=d.plan_v3.get('canonical_part_type_id') if d else stored.type_id if stored else None
        if not tid:
            classified=classify(dict(title=p.name,category=categories.get(p.category_id,''),subcategory=categories.get(p.subcategory_id,''),manufacturer=values.get('manufacturer',''),model=values.get('model','')))
            tid=classified.get('type_id')
            if tid:pl=placement(classified)
        result[p.id]=dict(type_id=tid,placement=pl,values=values,provenance=saved.get('provenance',{}),vehicle=v,link=d)
    return result

def sources(db,contexts,parts,account,state):
    types={c['type_id'] for c in contexts.values() if c['type_id']};oems={oem(p.oem_number) for p in parts if p.oem_number}
    if not types and not oems:return [],False
    model,brand=aliased(Entity),aliased(Entity)
    query=select(Mapping,Offer,Source,Path,model,brand,Variant,Placement).join(Path,Path.id==Mapping.catalogue_path_id).join(Offer,Offer.id==Path.offer_id).join(Source,Source.id==Offer.source_id).join(model,model.id==Path.model_id).join(brand,brand.id==model.parent_id).join(Variant,Variant.id==Mapping.variant_id).join(Placement,Placement.id==Mapping.placement_id).where(Mapping.snapshot_sha==state.snapshot_sha,Mapping.quality.in_(['verified_rule','verified_owner']),or_(Mapping.type_id.in_(types),oem_sql(Offer.properties.op('->>')('oem')).in_(oems)))
    # Limit source models before materialization; no per-card full-catalogue scan.
    models={(identity(c['values'].get('manufacturer')),identity(c['values'].get('model'))) for c in contexts.values() if c['values'].get('manufacturer') and c['values'].get('model')}
    if models:query=query.where(or_(*[(brand.normalized_name==b)&(model.normalized_name==m) for b,m in models]))
    records=[];rows=db.execute(query.order_by(Mapping.id).limit(MAX_SOURCE_ROWS+1)).all();truncated=len(rows)>MAX_SOURCE_ROWS
    for mapping,offer,provider,path,m,b,variant,pl in rows[:MAX_SOURCE_ROWS]:
        raw=path.raw;props=offer.properties
        current=source_record(key='v2:'+path.id,kind='v2',path_id=path.id,offer_id=offer.id,model_id=m.id,provider=provider.name,article=offer.source_article,source_url=props['source_url'],title=props['part_name'],oem=props.get('oem'),category=raw['category'],subcategory=raw['subcategory'],manufacturer=b.name,model=m.name,generation=raw.get('generation') or m.details.get('generation',''),year_from=raw.get('year_from'),year_to=raw.get('year_to'),side=raw.get('side',''),position=raw.get('position',''),raw=raw)
        stale=current['sha']!=mapping.source_sha
        records.append(dict(kind='v2',stale=stale,offer_id=offer.id,provider=provider.name,article=offer.source_article,properties=offer.properties,
            offer_date=offer.observed_at,type_id=mapping.type_id,placement=dict(id=pl.id,side=pl.side,position=pl.position,details=pl.details),
            attrs=variant.attributes,features=mapping.evidence.get('resolved_features') or mapping.evidence.get('normalization',{}).get('features',{}),
            raw=path.raw,manufacturer=b.name,model=m.name,quality=mapping.quality,evidence_id=mapping.id,source_sha=mapping.source_sha))
    # v1 remains tenant-scoped. Full-phrase verified rules prove function only;
    # no fuzzy name/OEM substitution is used as interchangeability evidence.
    root,sub=aliased(Category),aliased(Category)
    stmt=select(AletoTaxonomy,AletoOffer,AletoModel,root,sub).join(AletoOffer,(AletoOffer.id==AletoTaxonomy.offer_id)&(AletoOffer.account_id==account)).join(AletoModel,(AletoModel.id==AletoTaxonomy.model_id)&(AletoModel.account_id==account)).join(root,(root.id==AletoTaxonomy.category_id)&(root.account_id==account)).outerjoin(sub,(sub.id==AletoTaxonomy.subcategory_id)&(sub.account_id==account)).where(AletoTaxonomy.account_id==account,root.archived.is_(False))
    if models:stmt=stmt.where(or_(*[(func.lower(AletoModel.manufacturer)==b)&(func.lower(AletoModel.model)==m) for b,m in models]))
    elif oems:stmt=stmt.where(oem_sql(AletoOffer.oem).in_(oems))
    rows=db.execute(stmt.order_by(AletoTaxonomy.id).limit(MAX_SOURCE_ROWS+1)).all();truncated|=len(rows)>MAX_SOURCE_ROWS
    aliases=[dict(id=a.id,type_id=a.type_id,criteria=a.criteria,enabled=a.enabled) for a in db.scalars(select(CanonicalAlias).where(CanonicalAlias.id.in_(state.policy.get('alias_ids',[]))))]
    for path,offer,m,c,s in rows[:MAX_SOURCE_ROWS]:
        if s and s.archived:continue
        raw=dict(title=offer.title,oem=offer.oem,manufacturer=m.manufacturer,model=m.model,category=c.name,subcategory=s.name if s else path.raw_subcategory)
        match=classify(raw,aliases)
        if match.get('type_id') not in types or not match.get('quality','').startswith('verified'):continue
        pl=placement(match)
        records.append(dict(kind='v1',stale=False,offer_id=offer.id,provider=offer.source,article=offer.source_article,properties=dict(part_name=offer.title,oem=offer.oem,condition=offer.condition,source_url=offer.source_url),offer_date=offer.observed_at,
            type_id=match['type_id'],placement=pl,attrs={},features=match['features'],raw={},manufacturer=m.manufacturer,model=m.model,quality=match['quality'],evidence_id='v1:'+path.id,source_sha=digest(raw)))
    return records,truncated

def relevance(part,ctx,source):
    if not ctx['type_id'] or source['type_id']!=ctx['type_id']:return None,'function_unverified'
    v=ctx['values'];pl=ctx['placement'] or {};other=source['placement'];differences=[]
    if not v.get('manufacturer') or not v.get('model'):differences.append('Модель автомобіля не уточнена')
    elif identity(v['manufacturer'])!=identity(source['manufacturer']) or identity(v['model'])!=identity(source['model']):return None,'model_conflict'
    for field in ('side','position'):
        a=pl.get(field,'unknown');b=other.get(field,'unknown')
        if a!='unknown' and b!='unknown' and a!=b:return None,'installation_conflict'
        if a!=b:differences.append('Установча позиція не повністю уточнена')
    if pl.get('details',{})!=other.get('details',{}):differences.append('Відмінні або неповні ознаки встановлення')
    title_models=source['features'].get('title_models',[])
    if title_models and identity(source['model']) not in {identity(m) for m in title_models}:return None,'title_model_conflict'
    attrs={**source['attrs'],**{k:val for k,val in source['raw'].items() if val not in (None,'')}}
    for key in ('generation','engine','engine_code','fuel_type','transmission','drive','body_type'):
        value=attrs.get(key)
        if value:
            own=v.get(key) or (v.get('engine') if key=='engine_code' else '')
            if own and identity(str(own))!=identity(str(value)):return None,'configuration_conflict'
            if not own:differences.append('Не уточнено '+key)
    year=v.get('year')
    if year and ((attrs.get('year_from') and year<int(attrs['year_from'])) or (attrs.get('year_to') and year>int(attrs['year_to']))):return None,'year_conflict'
    labels=source['features'].get('title_year_labels',[])
    for label in labels:
        dates=re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)',label)
        if year and dates:
            if len(dates)==2 and '-' in label or len(dates)==2 and '–' in label:
                if not int(dates[0])<=year<=int(dates[1]):return None,'year_conflict'
            elif str(year) not in dates:return None,'year_conflict'
        elif label:differences.append('Період моделі у джерелі не підтверджено')
    a=assess(ctx['type_id'],v,source['features'],v,ctx['provenance'])
    if a['conflicting_fields']:return None,'configuration_conflict'
    if a['missing_or_unverified']:differences.append('Застосовність потребує перевірки: '+', '.join(a['missing_or_unverified']))
    features=source['features'];own=surface(dict(title=part.name+' '+part.compatibility_notes+' '+part.description,manufacturer=v.get('manufacturer',''),model=v.get('model','')))['features']
    for key,values in features.items():
        if not values or key in ('title_models','title_year_labels','fuel_labels','powertrain_labels','drive_labels','engine_codes','option_labels'):continue
        if own.get(key)!=values:differences.append('Не підтверджена ознака '+key)
    cosmetic=source.get('_cosmetic',[])
    if cosmetic:differences.append('Косметичні відмінності: '+', '.join(cosmetic))
    if oem(part.oem_number)!=oem(source['properties'].get('oem')) or not oem(part.oem_number):differences.append('OEM відрізняється або не підтверджено')
    condition=CONDITIONS.get(identity(source['properties'].get('condition')),'unknown')
    if part.condition=='unknown' or condition=='unknown' or part.condition!=condition:differences.append('Стан не збігається або невідомий')
    return sorted(set(differences)),None

def guidance(db,parts,account,now=None):
    now=now or utcnow();state=db.get(CanonicalState,1);revision=db.get(CatalogueState,1)
    base=dict(policy=VERSION,age_days=AGE_DAYS,catalogue_revision=revision.revision if revision else None,snapshot=state.snapshot_sha if state else None)
    empty={p.id:dict(part_id=p.id,level='D',label='Ціну не визначено',cohorts=[],examples=[],offer_count=0,reasons={},seller_price=str(p.selling_price) if p.selling_price is not None else None,seller_currency=p.currency,**base) for p in parts}
    if not state or not state.snapshot_sha or state.policy.get('rules_sha')!=RULE_FINGERPRINT:
        for row in empty.values():row['reasons']={'unpublished_or_stale_canonical':1}
        return empty
    contexts=context(db,parts,account);records,truncated=sources(db,contexts,parts,account,state)
    p2=latest_prices(db,Price,{s['offer_id'] for s in records if s['kind']=='v2' and not s['stale']},now)
    p1=latest_prices(db,AletoPrice,{s['offer_id'] for s in records if s['kind']=='v1' and not s['stale']},now,account)
    by_type=defaultdict(list);cosmetics={}
    for s in records:
        title=s['properties'].get('part_name','')
        if title not in cosmetics:cosmetics[title]=surface(dict(title=title))['cosmetic']
        s['_cosmetic']=cosmetics[title]
        relevant_attrs={**s['attrs'],**{k:v for k,v in s['raw'].items() if v not in (None,'')}}
        s['_relevance_key']=digest([s['type_id'],s['placement'],{k:relevant_attrs.get(k) for k in ('generation','engine','engine_code','fuel_type','transmission','drive','body_type','year_from','year_to')},s['features'],s['manufacturer'],s['model'],s['properties'].get('oem'),s['properties'].get('condition'),s['_cosmetic']])
        s['_cohort_key']=digest([oem(s['properties'].get('oem')),CONDITIONS.get(identity(s['properties'].get('condition')),'unknown'),{k:s['placement'].get(k) for k in ('side','position','details')},{k:s['attrs'].get(k) or '' for k in ('generation','year_from','year_to','engine','engine_code','fuel_type','transmission','drive')},{k:v for k,v in s['features'].items() if k not in ('title_models','title_year_labels')}])
        by_type[s['type_id']].append(s)
    projections={}
    for part in parts:
        ctx=contexts[part.id];pl=ctx['placement'] or {}
        projection_key=digest([ctx['type_id'],{k:pl.get(k) for k in ('side','position','details')},ctx['values'],ctx['provenance'],part.name,part.oem_number,part.condition,part.compatibility_notes,part.description])
        if projection_key in projections:
            empty[part.id].update({k:v for k,v in projections[projection_key].items() if k not in ('part_id','seller_price','seller_currency')});continue
        groups=defaultdict(dict);examples={};reasons=Counter();seen={};relevance_cache={}
        for src in by_type[contexts[part.id]['type_id']]:
            if src['stale']:reasons['stale_source_mapping']+=1;continue
            if src['offer_date']>now:reasons['future_source_observation']+=1;continue
            signature=src['_relevance_key']
            if signature not in relevance_cache:relevance_cache[signature]=relevance(part,contexts[part.id],src)
            original,reason=relevance_cache[signature];differences=list(original) if original is not None else None
            if reason:reasons[reason]+=1;continue
            price=(p2 if src['kind']=='v2' else p1).get(src['offer_id'])
            if not price:reasons['missing_or_future_observation']+=1;continue
            if price.observed_at<now-timedelta(days=AGE_DAYS):reasons['stale_observation']+=1;continue
            if price.observed_at!=src['offer_date']:differences.append('Стан не прив’язаний до дати ціни')
            if not any(v is not None and v.is_finite() and v>0 for v in (price.price_uah,price.price_usd)):reasons['missing_price']+=1;continue
            if truncated:differences.append('Джерельну вибірку обмежено; точний орієнтир недоступний')
            url=safe_url(price.source_url)
            if not url:reasons['missing_source_url']+=1;continue
            for currency,amount in [('UAH',price.price_uah),('USD',price.price_usd)]:
                if amount is None or not amount.is_finite() or amount<=0:continue
                # Same source/article across v1/v2 and multiple model/path rows
                # is one ad. Prefer latest; conflicting duplicate identity never
                # contributes to a reliable cohort.
                ident=(identity(src['provider']),src['article'],currency)
                entry=dict(source=src['provider'],article=src['article'],amount=str(amount),currency=currency,observed_at=price.observed_at.isoformat(),date_kind='price_observation_not_publication',url=url,
                    oem=src['properties'].get('oem'),condition_raw=src['properties'].get('condition'),condition=CONDITIONS.get(identity(src['properties'].get('condition')),'unknown'),differences=differences,quality=src['quality'],evidence_id=src['evidence_id'],source_sha=src['source_sha'],observation_id=price.id)
                group_key=digest([src['_cohort_key'],currency])
                old=seen.get(ident)
                if old and old['entry']['observed_at']>entry['observed_at']:continue
                if old and old['entry']['observed_at']==entry['observed_at'] and ((old['entry']['amount'],old['key'])!=(entry['amount'],group_key) or old.get('conflict')):
                    reasons['conflicting_duplicate']+=1;old['entry']['differences']=['Суперечливе повторне оголошення'];old['exact']=False;old['conflict']=True;continue
                seen[ident]=dict(entry=entry,key=group_key,exact=not differences)
        for ident,match in seen.items():
            if match['exact']:groups[(match['key'],match['entry']['currency'])][ident]=match['entry']
            else:examples[ident]=match['entry']
        cohorts=[]
        for (key,currency),entries in sorted(groups.items()):
            rows=sorted(entries.values(),key=lambda e:(e['source'],e['article']));values=[Decimal(e['amount']) for e in rows];n=len(rows)
            cohorts.append(dict(id=key,currency=currency,level='A' if n>=3 else 'B',match='exact_oem_verified_function',offer_count=n,minimum=str(min(values)) if n>=3 else None,maximum=str(max(values)) if n>=3 else None,median=str(median(values)) if n>=3 else None,observed_at=max(e['observed_at'] for e in rows),examples=rows[:10],evidence_hash=digest(rows)))
        if not contexts[part.id]['type_id']:reasons['missing_constructive_identity']+=1
        elif not by_type[contexts[part.id]['type_id']]:reasons['no_verified_source_mapping']+=1
        row=empty[part.id];row.update(cohorts=cohorts,examples=sorted(examples.values(),key=lambda e:(e['source'],e['article'],e['currency']))[:10],example_count=len(examples),example_evidence_hash=digest(sorted(examples.values(),key=lambda e:(e['source'],e['article'],e['currency']))),offer_count=len({(e['entry']['source'],e['entry']['article']) for e in seen.values()}),reasons=dict(reasons),truncated=truncated)
        row['level']='A' if any(c['level']=='A' for c in cohorts) else 'B' if cohorts else 'C' if examples else 'D'
        row['label']={'A':'Ринковий орієнтир','B':'Мало даних','C':'Приклади схожих запчастин','D':'Ціну не визначено'}[row['level']]
        projections[projection_key]=row
    return empty
