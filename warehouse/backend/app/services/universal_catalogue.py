"""Reviewed PRD preparation over existing CanonicalType/Placement and Run storage.

No source/network calls. No inventory writes. Counts are not fitment evidence.
"""
from collections import Counter,defaultdict
from pydantic import BaseModel,ConfigDict,Field,model_validator
from typing import Literal
from app.services.catalogue_format import digest
from app.services.canonical_rules import norm,type_record,sid,TYPES
from app.services.catalogue_carpot_sections import SECTIONS,SUBCATEGORIES
from app.schemas.vehicle_configuration import FIELDS

VERSION='carpot.universal.review.1'

class FitmentRule(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    id:str=Field(min_length=1,max_length=100)
    version:int=Field(ge=1,strict=True)
    when:dict[str,list[str|int|bool]]=Field(min_length=1,max_length=20)
    effect:Literal['confirmed','incompatible']
    priority:int=Field(default=0,ge=0,le=1000,strict=True)
    evidence:str=Field(min_length=10,max_length=2000)
    explanation:str=Field(min_length=5,max_length=1000)
    @model_validator(mode='after')
    def bounded(self):
        if not set(self.when)<=FIELDS-{'vin'}:raise ValueError('Unsupported condition field')
        if any(not values or len(values)>50 or any(len(str(v))>200 for v in values) for values in self.when.values()):raise ValueError('Bounded exact conditions required')
        return self


def evaluate(rules,configuration):
    """Exact, verified facts only. Any contradictory reviewed evidence is reviewable."""
    if configuration.get('conflicts'):return dict(status='unknown',decision='needs_review',matched=[],conflicts=['vehicle_configuration'],missing=[])
    values=configuration.get('values',{});quality=configuration.get('provenance',{});matched=[];missing=set()
    for raw in rules:
        rule=FitmentRule.model_validate(raw);unknown=[];different=False
        for field,allowed in rule.when.items():
            actual=values.get(field)
            if actual is None or quality.get(field,{}).get('confidence')!='verified':unknown.append(field)
            elif field=='options':
                # Missing options cannot disprove installation without an explicit complete list.
                if not set(allowed)<=set(actual):different=True
                if not values.get('options_complete') or quality.get('options_complete',{}).get('confidence')!='verified':unknown.append('options_complete')
            elif actual not in allowed:different=True
        if not different:
            missing.update(unknown)
            if not unknown:matched.append(rule.model_dump())
    effects={r['effect'] for r in matched}
    # Priority orders explanations; it never silently overrides contrary evidence.
    matched.sort(key=lambda r:(-r['priority'],r['id'],r['version']))
    status='unknown' if len(effects)!=1 else next(iter(effects))
    return dict(status=status,decision={'unknown':'needs_review','confirmed':'applicable','incompatible':'incompatible'}[status],matched=matched,conflicts=[r['id'] for r in matched] if len(effects)>1 else [],missing=sorted(missing))

class PlacementEvidence(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    side:Literal['left','right','unknown']='unknown'
    position:Literal['front','rear','unknown']='unknown'
    mount:list[Literal['upper','lower','inner','outer']]=Field(default_factory=list,max_length=4)
    ordinal:int|None=Field(default=None,ge=1,le=100,strict=True)
    evidence:str=Field(min_length=10,max_length=2000)
    @model_validator(mode='after')
    def consistent(self):
        if any(a in self.mount and b in self.mount for a,b in [('upper','lower'),('inner','outer')]):raise ValueError('Conflicting mount')
        self.mount=sorted(set(self.mount))
        return self

class ReviewedType(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    source_id:int=Field(gt=0,strict=True)
    source_sha:str=Field(pattern='^[a-f0-9]{64}$')
    name_uk:str=Field(min_length=2,max_length=200)
    category:str=Field(min_length=2,max_length=100)
    subcategory:str=Field(min_length=2,max_length=100)
    kind:Literal['part','consumable','equipment','tool','chemical','review']
    target_id:str|None=Field(default=None,max_length=36)
    evidence:str=Field(min_length=10,max_length=2000)
    synonyms:list[str]=Field(default_factory=list,max_length=50)
    rules:list[FitmentRule]=Field(default_factory=list,max_length=100)
    # Absence means one unplaced candidate, never automatic left/right multiplication.
    placements:list[PlacementEvidence]=Field(default_factory=list,max_length=100)
    @model_validator(mode='after')
    def corporate(self):
        if self.category not in SECTIONS:raise ValueError('Unknown corporate category')
        if self.subcategory not in {label for label,_ in SUBCATEGORIES[SECTIONS.index(self.category)]}:raise ValueError('Unknown corporate subcategory')
        if not any('а'<=c.casefold()<='я' or c.casefold() in 'іїєґ' for c in self.name_uk) or any(c.casefold() in 'ыэёъ' for c in self.name_uk):raise ValueError('Reviewed Ukrainian name required')
        if any(not x or len(x)>200 for x in self.synonyms):raise ValueError('Invalid synonym')
        if len({r.id for r in self.rules})!=len(self.rules):raise ValueError('Duplicate rule identity')
        return self


def prd_record(row):
    fields=('id','assemblygroupdescription','description','normalizeddescription','usagedescription')
    if type(row.get('id')) is not int or row['id']<=0:raise ValueError('PRD source id required')
    result={k:row.get(k) for k in fields}
    if any(v is not None and (not isinstance(v,str) or len(v)>5000) for k,v in result.items() if k!='id'):raise ValueError('Invalid source text')
    return dict(source_key=f"td1q2018:prd:{row['id']}",source_sha=digest(result),original=result)


def prepare(rows,reviews=(),known=None):
    """Streaming source scan; explicit reviewed decisions are checksum-bound to originals."""
    decisions={};sources={};issues=[];duplicates=0;counts=Counter();prepared={};known={t['id']:t for t in (TYPES.values() if known is None else known)}
    names=defaultdict(set);bindings=defaultdict(set)
    for t in known.values():
        names[norm(t['name'])].add(t['id'])
        for ref in t.get('provenance',{}).get('universal_sources',[]):bindings[ref['source_key']].add(t['id'])
    for raw in reviews:
        r=ReviewedType.model_validate(raw)
        if r.source_id in decisions:raise ValueError('Duplicate reviewed source id')
        decisions[r.source_id]=r
    for raw in rows:
        source=prd_record(raw);id=raw['id']
        if id in sources:
            if sources[id]!=source['source_sha']:raise ValueError('Conflicting duplicate source id')
            duplicates+=1;continue
        sources[id]=source['source_sha'];r=decisions.get(id)
        if not r or r.source_sha!=source['source_sha']:
            issues.append(dict(source_id=id,source_key=source['source_key'],reason='source_changed' if r else 'needs_review',original=source['original']));continue
        counts[r.kind]+=1
        if r.kind=='review':issues.append(dict(source_id=id,reason='classification_needs_review'));continue
        if r.kind!='part':continue
        candidate=type_record(r.name_uk,r.category,r.subcategory)
        if r.target_id:
            if r.target_id not in known:raise ValueError('Explicit target canonical ID not found')
            candidate={k:known[r.target_id][k] for k in ('id','identity_key','name','category','subcategory')}
        elif names[norm(r.name_uk)]-{candidate['id']}:
            issues.append(dict(source_id=id,reason='explicit_existing_id_required',original=source['original']));continue
        if bindings[source['source_key']]-{candidate['id']}:
            issues.append(dict(source_id=id,reason='source_rebind_requires_explicit_migration'));continue
        record=prepared.setdefault(candidate['id'],{**candidate,'display_name_uk':r.name_uk,'corporate_path':[r.category,r.subcategory],'sources':[],'rules':[],'placements':[],'synonyms':[]})
        if record['display_name_uk']!=r.name_uk:issues.append(dict(source_id=id,reason='display_name_conflict'));continue
        if record['corporate_path']!=[r.category,r.subcategory]:issues.append(dict(source_id=id,reason='corporate_category_conflict'));continue
        record['sources'].append({**source,'evidence':r.evidence})
        for key in ('rules','placements','synonyms'):
            for v in getattr(r,key):
                value=v.model_dump(exclude_none=True) if isinstance(v,BaseModel) else v
                if value not in record[key]:record[key].append(value)
    for id in set(decisions)-set(sources):issues.append(dict(source_id=id,reason='missing_source'))
    result=dict(version=VERSION,types=list(prepared.values()),review=issues,counts=dict(source_records=len(sources),duplicate_source_rows=duplicates,physical_types=len(prepared),review=len(issues),excluded=sum(n for k,n in counts.items() if k!='part'),classifications=dict(counts)),coverage='unverified',factory_bom=False)
    result['sha256']=digest(result)
    return result


def batch_preview(db,request):
    from sqlalchemy import select
    from app.models.canonical import CanonicalType
    known_by_id={id:dict(t) for id,t in TYPES.items()}
    known_by_id.update({t.id:dict(id=t.id,identity_key=t.identity_key,name=t.name,category=t.category,subcategory=t.subcategory,provenance=t.provenance) for t in db.scalars(select(CanonicalType).order_by(CanonicalType.id))})
    known=sorted(known_by_id.values(),key=lambda t:t['id'])
    if digest(request['rows'])!=request['input_sha']:raise ValueError('Source checksum mismatch')
    result=prepare(request['rows'],request['reviews'],known)
    report=dict(kind='universal-preview',request=request,prepared=result,basis_sha=digest(known))
    return dict(report=report,token=digest(report),snapshot_sha=None)


def publish_batch(db,preview_id,token,actor):
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert
    from fastapi import HTTPException
    from app.models.canonical import CanonicalRun,CanonicalType,CanonicalPlacement
    from app.services.canonical_rules import placement
    prior=db.get(CanonicalRun,preview_id)
    if not prior or prior.status!='done' or prior.report.get('kind')!='universal-preview' or prior.token!=token:raise HTTPException(409,'Потрібен завершений preview каталогу')
    current=batch_preview(db,prior.report['request'])
    if current['token']!=token:raise HTTPException(409,'Каталог або джерело змінилися; повторіть preview')
    prepared=current['report']['prepared']
    if prepared['review']:raise HTTPException(409,'Спочатку перегляньте всі неоднозначні записи пакета')
    for row in prepared['types']:
        t=db.get(CanonicalType,row['id'])
        if t and any(getattr(t,k)!=row[k] for k in ('identity_key','name','category','subcategory')):raise HTTPException(409,'Канонічний ID має інший зміст')
        old=t.provenance if t else {}
        sources={s['source_key']:s for s in old.get('universal_sources',[])}
        for source in row['sources']:
            if source['source_key'] in sources and sources[source['source_key']]['source_sha']!=source['source_sha']:raise HTTPException(409,'Джерельний ID змінився; потрібне окреме рішення')
            sources[source['source_key']]=source
        existing_rules={r['id']:r for r in old.get('fitment_rules',[])}
        for rule in row['rules']:
            if rule['id'] in existing_rules and existing_rules[rule['id']]!=rule:raise HTTPException(409,'Зміна правила потребує нової доказової ідентичності')
            existing_rules[rule['id']]=rule
        provenance={**old,'universal_publication':VERSION,'universal_sources':list(sources.values()),'fitment_rules':list(existing_rules.values()),'universal_reviewed_by':actor,'universal_preview_id':preview_id,'declared_placements':list({digest(p):p for p in old.get('declared_placements',[])+row['placements']}.values()),'display_name_uk':row['display_name_uk'],'corporate_path':row['corporate_path'],'synonyms':sorted(set(old.get('synonyms',[])+row['synonyms']))}
        if t:t.provenance=provenance
        else:db.add(CanonicalType(**{k:row[k] for k in ('id','identity_key','name','category','subcategory')},provenance=provenance));db.flush()
        for source_place in row['placements'] or [dict(side='unknown',position='unknown')]:
            p=placement(dict(type_id=row['id'],installation={**source_place,'side':source_place.get('side','unknown'),'position':source_place.get('position','unknown'),'ordinal':[source_place['ordinal']] if source_place.get('ordinal') else []}))
            db.execute(insert(CanonicalPlacement).values(**p).on_conflict_do_nothing(index_elements=['id']))
    return dict(report=dict(kind='universal-publication',counts=prepared['counts'],preview_id=preview_id,approved_by=actor,inventory_writes=0),token=token,snapshot_sha=None)
