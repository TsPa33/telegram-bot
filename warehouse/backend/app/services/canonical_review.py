"""Grouped owner review: exact scope, exhaustive dry-run, explicit append-only approval."""
from collections import defaultdict
from sqlalchemy import select,text
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException
from app.models.canonical import CanonicalType as Type,CanonicalAlias as Alias,CanonicalRun as Run
from app.services.canonical_catalogue import analyze,global_inputs,latest_aliases
from app.services.canonical_rules import TYPES,LEX,RULES,norm,classify,conditions_match,placement
from app.services.catalogue_format import digest
from app.services.catalogue_import import LOCK
from app.services.canonical_terms import alias_series

AMBIGUOUS={'комп','блок','блок керування','блок управління','датчик','датчик тиску','датчик давления','насос','камера','накладка','обшивка','проводка','пристрій','монітор','дисплей','форсунка','інше','пластик'}

def suggested(phrase):
    # Suggestions only. Never an association or a verification decision.
    tokens=phrase.split();matches=[]
    for label,rules in LEX.items():
        words=label.split()
        if words and any(tokens[i:i+len(words)]==words for i in range(max(0,len(tokens)-len(words)+1))):
            for rule in rules:matches.append((len(words),rule['type_id']))
    if not matches:return []
    longest=max(n for n,_ in matches)
    return sorted({tid for n,tid in matches if n==longest})

def group_key(source,outcome):
    p=outcome['evidence']['normalization']['phrase']
    return digest([suggested(p),norm(source['category']),norm(source['subcategory']),p,outcome.get('reason')])

def groups(db,offset=0,limit=50):
    aliases=latest_aliases(db);bucket={}
    for source in global_inputs(db):
        if source['kind']!='v2':continue
        result=classify(source,aliases)
        if result['quality'].startswith('verified'):continue
        key=group_key(source,result);phrase=result['evidence']['normalization']['phrase']
        g=bucket.setdefault(key,dict(id=key,phrase=phrase,category=source['category'],subcategory=source['subcategory'],reason=result.get('reason'),suggested_type_ids=suggested(phrase),records=0,offer_ids=set(),examples=[]))
        g['records']+=1;g['offer_ids'].add(source['offer_id'])
        if len(g['examples'])<5 and source['title'] not in g['examples']:g['examples'].append(source['title'])
    rows=[]
    for g in bucket.values():g['offers']=len(g.pop('offer_ids'));rows.append(g)
    rows.sort(key=lambda g:(-g['offers'],-g['records'],g['id']))
    return {'items':rows[offset:offset+limit],'total':len(rows),'suggestions_are_approvals':False}


def effective_conditions(draft):
    result={**draft.get('conditions',{}),'no_conflicts':True}
    rule=next((r for r in RULES['types'] if any(tid==draft['type_id'] for tid,t in TYPES.items() if t['name']==r['name'] and t['category']==r['category'] and t['subcategory']==r['subcategory'])),None)
    if rule:
        for flag in ('require_side','require_position'):
            if rule.get(flag):result[flag.removeprefix('require_')+'_known']=True
        if rule.get('default_position') or rule.get('require_rear_word'):result['position_known']=True
        if rule.get('require_rear_word'):result['forbidden_positions']=['front','unknown']
        if rule.get('require_mount'):result['mount']=[rule['require_mount']]
        if rule.get('forbidden_position'):result['forbidden_positions']=sorted(set(result.get('forbidden_positions',[])+[rule['forbidden_position']]))
        if rule.get('require_assembly'):result['assembly']=[rule['require_assembly']]
    return result


def rule_preview(db,draft):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
    target=db.get(Type,draft['type_id'])
    if not target and draft['type_id'] not in TYPES:raise HTTPException(404,'Канонічний тип не знайдено')
    if norm(draft['phrase']) in AMBIGUOUS:raise HTTPException(422,'Неповна функціональна назва не придатна для масового погодження; потрібне точніше правило або індивідуальне рішення')
    plan=analyze(db);aliases=latest_aliases(db);conditions=effective_conditions(draft)
    criteria={k:norm(draft.get(k,'')) for k in ('phrase','category','subcategory','manufacturer','model')}
    criteria['conditions']=conditions
    matched=[];exceptions=[];conflicts=[];samples=[];seen=set();will_link=0;unchanged=0
    for source in global_inputs(db):
        current=classify(source,aliases);parsed=current['evidence']['normalization']
        if parsed['phrase']!=criteria['phrase'] or any(criteria[k] and criteria[k]!=norm(source.get(k,'')) for k in ('category','subcategory','manufacturer','model')):continue
        example={k:source.get(k) for k in ('key','sha','title','manufacturer','model','oem')}
        if not conditions_match(conditions,source,parsed):exceptions.append({**example,'reason':'Rule conditions are missing or contradicted'});continue
        if current.get('type_id') and current['type_id']!=draft['type_id']:
            conflicts.append({**example,'previous_type_id':current['type_id']});continue
        simulated=classify(source,aliases+[{'id':'proposal-only','type_id':draft['type_id'],'criteria':criteria,'enabled':True}])
        if not simulated.get('type_id') or simulated['type_id']!=draft['type_id'] or (current.get('type_id') and placement(current)['id']!=placement(simulated)['id']):
            conflicts.append({**example,'reason':'Approval conflicts with an existing decision or installation'});continue
        if current.get('type_id'):unchanged+=1
        else:will_link+=1
        matched.append([source['key'],source['sha']])
        signature=(source.get('model'),parsed['side'],parsed['position'],bool(source.get('oem')),tuple(parsed['features'].get('fuel_labels',[])))
        if signature not in seen and len(samples)<12:samples.append({**example,'source_features':parsed['features']});seen.add(signature)
    key=alias_series(criteria)
    previous=db.scalar(select(Alias).where(Alias.series_key==key).order_by(Alias.revision.desc()).limit(1))
    revision=previous.revision if previous else 0
    report=dict(kind='rule-preview',criteria=criteria,type_id=draft['type_id'],evidence=draft['evidence'],expected_revision=draft.get('expected_revision',0),current_revision=revision,
        matched_count=len(matched),will_link_count=will_link,unchanged_count=unchanged,exception_count=len(exceptions),conflict_count=len(conflicts),examples=samples,exceptions=exceptions[:12],conflicts=conflicts[:12],
        matched_digest=digest(matched),snapshot_sha=plan['snapshot_sha'],committed=False,all_members_checked=True)
    return {'report':report,'snapshot_sha':plan['snapshot_sha'],'token':digest(report)}


def approve_rule(db,preview_id,token,actor):
    previous=db.get(Run,preview_id)
    if not previous or previous.status!='done' or previous.report.get('kind')!='rule-preview' or previous.token!=token:raise HTTPException(409,'Потрібна завершена перевірка групового правила')
    p=previous.report;criteria=p['criteria'];draft={**{k:criteria[k] for k in ('phrase','category','subcategory','manufacturer','model')},'conditions':criteria['conditions'],'type_id':p['type_id'],'evidence':p['evidence'],'expected_revision':p['expected_revision']}
    current=rule_preview(db,draft)
    if current['token']!=token:raise HTTPException(409,'Джерела або правила змінилися; повторіть групову перевірку')
    if p['conflict_count'] or not p['matched_count'] or p['current_revision']!=p['expected_revision']:raise HTTPException(409,'Є конфлікти, немає відповідностей або revision застаріла')
    if not db.get(Type,p['type_id']):db.execute(insert(Type).values(**TYPES[p['type_id']]).on_conflict_do_nothing(index_elements=['id']))
    key=alias_series(criteria)
    alias=Alias(series_key=key,revision=p['current_revision']+1,type_id=p['type_id'],enabled=True,criteria=criteria,evidence=p['evidence'],actor_id=actor)
    db.add(alias);db.flush()
    return {'report':{**p,'kind':'rule-approval','alias_id':alias.id,'alias_revision':alias.revision,'preview_id':preview_id,'approved_by':actor,'committed':True,'canonical_publication_changed':False},'token':token,'snapshot_sha':p['snapshot_sha']}
