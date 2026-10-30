"""Managed plan in existing DismantlingItem; no secondary stock ledger."""
from collections import Counter,defaultdict
from types import SimpleNamespace
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.models import Vehicle,DismantlingItem,Part,Operation,DismantlingRequest
from app.models.canonical import CanonicalState
from app.models.catalogue import CatalogueState
from app.services.inventory import owned,snapshot,record
from app.services.vehicle_configuration import basis,latest
from app.services.catalogue_format import digest
from app.services.canonical_rules import classify,placement,norm,sid,RULE_FINGERPRINT
from app.services.dismantling_preview import preview
from app.schemas.dismantling_v3 import PlanPreview

VERSION='carpot.managed-plan.2b.2'
PART_STATE_FIELDS=('id','vehicle_id','checklist_category_id','quantity','reserved_quantity','archived')
def rows_for(db,v):return list(db.scalars(select(DismantlingItem).where(DismantlingItem.account_id==v.account_id,DismantlingItem.vehicle_id==v.id).order_by(DismantlingItem.id)))
def state(db,v,rows=None):
    rows=rows_for(db,v) if rows is None else rows
    # Public etags must never be a guessing oracle for hidden prices/costs.
    parts=[dict(row) for row in db.execute(select(*(getattr(Part,k) for k in PART_STATE_FIELDS)).where(Part.account_id==v.account_id,Part.vehicle_id==v.id).order_by(Part.id)).mappings()]
    ops=list(db.scalars(select(Operation.id).where(Operation.account_id==v.account_id,Operation.vehicle_id==v.id).order_by(Operation.id)))
    # JSON columns are already primitives; snapshot converts top-level dates/money.
    return digest([v.id,v.account_id,basis(v),v.archived,v.dismantling_v3,[snapshot(r) for r in rows],parts,ops])
def inspection(r):return r.plan_v3.get('inspection') or ('present' if r.received_at or r.status=='dismantled' else 'absent' if r.status=='absent' else 'unchecked')
def protected(r):return bool(r.received_at or r.part_id)
def listing(db,v):
    from app.services.dismantling_bulk import eligibility
    rows=rows_for(db,v);parts={p.id:p for p in db.scalars(select(Part).where(Part.account_id==v.account_id,Part.vehicle_id==v.id))}
    sales=defaultdict(int);other_decreases=set()
    for op in db.scalars(select(Operation).where(Operation.account_id==v.account_id,Operation.vehicle_id==v.id,Operation.type.in_(['sale','write_off','correction']))):
        before=(op.before or {}).get('quantity');after=(op.after or {}).get('quantity')
        if type(before) is not int or type(after) is not int:
            other_decreases.add(op.part_id);continue # Missing historical facts cannot prove a sale.
        decrease=before-after
        if decrease>0:
            if op.type=='sale':sales[op.part_id]+=decrease
            else:other_decreases.add(op.part_id)
    items=[]
    for r in rows:
        p=parts.get(r.part_id)
        operational='sold' if p and p.quantity==0 and sales[p.id]>=r.quantity and p.id not in other_decreases else 'received' if r.received_at else 'dismantled' if r.status=='dismantled' else 'not_dismantled'
        items.append(dict(id=r.id,name=r.name,position=r.position,category=r.category_name,subcategory=r.subcategory_name,included=r.included,inspection=inspection(r),reason=r.plan_v3.get('reason','' if r.included else 'Збережене виключення legacy'),operational_state=operational,protected=protected(r),part_archived=bool(p and p.archived),selectable=not v.archived and not protected(r) and bool(r.plan_v3.get('placement_id')),eligibility=eligibility(r,archived=v.archived or bool(p and p.archived)),confirmation_source=r.plan_v3.get('inspection_source') or ('historical_workflow' if inspection(r)=='present' else None),quantity=r.quantity,part_id=r.part_id,applicability=r.plan_v3.get('snapshot',{}).get('applicability_status','unknown'),canonical_part_type_id=r.plan_v3.get('canonical_part_type_id'),placement_id=r.plan_v3.get('placement_id'),reference_prices=r.plan_v3.get('snapshot',{}).get('reference_prices',[])))
    items.sort(key=lambda i:(i['category'],i['subcategory'],i['name'],i['position'],i['id']))
    canonical=db.get(CanonicalState,1);catalogue=db.get(CatalogueState,1);configuration_source=latest(db,v,v.account_id)
    from app.services.dismantling_catalog import scoped_catalogue_digest
    local_sha=scoped_catalogue_digest(db,v.account_id,v)
    return dict(configuration_stale=bool(v.dismantling_v3) and (v.dismantling_v3.get('vehicle_basis')!=basis(v) or v.dismantling_v3.get('configuration_source_id')!=(configuration_source.get('id') if configuration_source else None)),catalogue_changed=bool(v.dismantling_v3) and (v.dismantling_v3.get('catalogue_snapshot')!=(canonical.snapshot_sha if canonical else None) or v.dismantling_v3.get('catalogue_revision')!=(catalogue.revision if catalogue else None) or v.dismantling_v3.get('local_catalogue_sha')!=local_sha),items=items,total=len(items),active=bool(v.dismantling_v3),archived=v.archived,etag=state(db,v,rows),revision=v.dismantling_v3.get('revision',0),configuration=v.dismantling_v3.get('configuration'),review_drafts=v.dismantling_v3.get('review_drafts',{}),pending_review=v.dismantling_v3.get('pending_review',[]),pending_count=len(v.dismantling_v3.get('pending_review',[])),catalogue_status=dict(published=bool(canonical and canonical.snapshot_sha),rules_current=bool(canonical and canonical.policy.get('rules_sha')==RULE_FINGERPRINT),fallback_used=not bool(canonical and canonical.snapshot_sha)),counts=dict(in_stock=sum(not p.archived and p.quantity>0 for p in parts.values()),unchecked=sum(i['inspection']=='unchecked' for i in items),dismantled=sum(i['operational_state']=='dismantled' for i in items),possible=sum(i['applicability'] in ('possible','unknown') for i in items),confirmed=sum(i['inspection']=='present' for i in items),excluded=sum(not i['included'] for i in items),received=sum(i['operational_state'] in ('received','sold') for i in items)))

def axes_match(a,b):
    if a['details'].get('ordinal') and b['details'].get('ordinal') and a['details']['ordinal']!=b['details']['ordinal']:return False
    return all(a[k]=='unknown' or b[k]=='unknown' or a[k]==b[k] for k in ('side','position')) and (not a['details']['mount'] or not b['details']['mount'] or a['details']['mount']==b['details']['mount'])
def make_preview(db,v,who,data,*,virtual_base=False):
    source=latest(db,v,v.account_id);source_id=source.get('id') if source else None
    prior=v.dismantling_v3.get('trial_input',{}) if not data.reset_trial and v.dismantling_v3.get('vehicle_basis')==basis(v) and v.dismantling_v3.get('configuration_source_id')==source_id else {}
    incoming=[{**f.model_dump(),'confidence':'reported'} for f in data.facts]
    replaced={f['field'] for f in incoming};kept=[(i,f) for i,f in enumerate(prior.get('facts',[])) if f['field'] not in replaced]
    index={old:new for new,(old,_) in enumerate(kept)}
    selected={field:index[i] for field,i in prior.get('selected',{}).items() if field not in replaced and i in index}
    selected.update({field:i+len(kept) for field,i in data.selected.items()})
    facts=[f for _,f in kept]+incoming
    if len(facts)>200:raise HTTPException(422,'Забагато пробних фактів; скиньте попередні уточнення')
    if any(f['field']=='options_complete' and f['value'] for f in facts):raise HTTPException(422,'Потрібна окрема підтверджена конфігурація')
    trial_input=dict(facts=facts,selected=selected)
    canonical=db.get(CanonicalState,1)
    options={'universal_base':True} if virtual_base and not (canonical and canonical.snapshot_sha) else {}
    generated=jsonable_encoder(preview(db,v,v.account_id,facts,selected,**options));existing=rows_for(db,v)
    legacy={};unclassified=[]
    for r in existing:
        if r.plan_v3.get('placement_id'):continue
        result=classify(dict(key=r.id,sha='',title=r.name,category=r.category_name,subcategory=r.subcategory_name,position=r.position,manufacturer=v.manufacturer,model=v.model))
        if result.get('type_id'):legacy[r.id]=(result['type_id'],placement(result))
        else:unclassified.append(r)
    # Index by constructive identity/context, not by market offer count.
    by_id={r.id:r for r in existing};exact_by_placement=defaultdict(list);bound_by_type=defaultdict(list);legacy_by_type=defaultdict(list);legacy_by_ref=defaultdict(list);unknown_by_category=defaultdict(list)
    for r in existing:
        if r.plan_v3:
            if r.plan_v3.get('placement_id'):exact_by_placement[r.plan_v3['placement_id']].append(r)
            bound_by_type[r.plan_v3.get('canonical_part_type_id')].append(r)
        else:
            legacy_by_ref[(r.source,r.catalog_key)].append(r)
            if r.id in legacy:legacy_by_type[legacy[r.id][0]].append(r)
            else:unknown_by_category[norm(r.category_name)].append(r)
    proposals=[];used=defaultdict(list);unknown_resolutions=set(data.resolutions)-{i['id'] for i in generated['items']}
    if unknown_resolutions:raise HTTPException(422,'Рішення не належить поточному preview')
    for item in generated['items']:
        pid=item['id'];tid=item['canonical_part_type_id'];exact=exact_by_placement[pid];possible_by_id={}
        for r in bound_by_type[tid]:
            old=r.plan_v3.get('snapshot',{})
            if old.get('installation_position') and axes_match(old['installation_position'],item['installation_position']):possible_by_id[r.id]=r
        for r in legacy_by_type[tid]:
            if axes_match(legacy[r.id][1],item['installation_position']):possible_by_id[r.id]=r
        for ref in item['source']:
            legacy_ref=ref.get('legacy_ref') or {}
            for r in legacy_by_ref[(legacy_ref.get('source'),legacy_ref.get('catalog_key'))]:possible_by_id[r.id]=r
        for r in unknown_by_category[norm(item['category'])]:possible_by_id[r.id]=r
        possible=[possible_by_id[key] for key in sorted(possible_by_id)]
        exact_legacy=[r for r in possible if r.id in legacy and legacy[r.id][1]['id']==pid]
        candidates=exact or possible
        action='link' if len(exact)==1 or (len(exact_legacy)==1 and len(possible)==1) else 'review' if candidates else 'new'
        target=exact[0].id if len(exact)==1 else exact_legacy[0].id if action=='link' else None
        saved_skip=v.dismantling_v3.get('skipped',{}).get(pid)
        if saved_skip and not exact:action='skip';target=None
        resolution=data.resolutions.get(pid)
        if resolution:
            action=resolution.action;target=resolution.item_id
            if action=='link' and target not in {r.id for r in candidates}:raise HTTPException(422,'Неприпустима legacy-позиція для зіставлення')
            if action=='new' and exact:raise HTTPException(409,'Канонічна позиція вже існує; не можна створити дублікат')
        if target:used[target].append(pid)
        proposals.append(dict(id=pid,item=item,action=action,target_id=target,manual=bool(resolution),reason=resolution.reason if resolution else saved_skip or '',candidates=[dict(id=r.id,name=r.name,position=r.position,protected=protected(r),included=r.included,inspection=inspection(r),reason=r.plan_v3.get('reason','')) for r in candidates],previous_snapshot=by_id[target].plan_v3.get('snapshot') if target in by_id else None))
    # Generic and more precise NEW positions can describe the same physical part.
    proposals_by_type=defaultdict(list)
    for proposal in proposals:proposals_by_type[proposal['item']['canonical_part_type_id']].append(proposal)
    for p in proposals:
        overlap=[]
        a=p['item']['installation_position']
        for q in proposals_by_type[p['item']['canonical_part_type_id']]:
            if p is q:continue
            b=q['item']['installation_position']
            broad=any((a[k]=='unknown')!=(b[k]=='unknown') for k in ('side','position')) or bool(a['details']['mount'])!=bool(b['details']['mount']) or bool(a['details'].get('ordinal'))!=bool(b['details'].get('ordinal'))
            if broad and axes_match(a,b):overlap.append(q['id'])
        p['overlap_ids']=overlap
        if overlap and p['action']=='new' and not p['manual']:p['action']='review';p['conflict']='Загальна та уточнена позиції можуть означати одну фізичну деталь'
    collisions={target for target,ids in used.items() if len(ids)>1}
    for p in proposals:
        if p['target_id'] in collisions:p['action']='review';p['conflict']='Одну legacy-позицію не можна прив’язати до кількох конструктивних позицій'
    counts=Counter(p['action'] for p in proposals)
    diffs=[]
    for p in proposals:
        old=p['previous_snapshot'];item=p['item']
        if old and digest(old)!=digest(item):diffs.append(dict(id=p['id'],name=item['name'],new_oem_variants=sorted({v['id'] for v in item['variants']}-{v['id'] for v in old.get('variants',[])}),prices_changed=old.get('reference_prices')!=item['reference_prices'],applicability_changed=old.get('applicability_status')!=item['applicability_status']))
    for p in proposals:p.pop('previous_snapshot',None)
    present={p['id'] for p in proposals}
    retained=[r.id for r in existing if r.plan_v3.get('placement_id') and r.plan_v3['placement_id'] not in present]
    old_values=v.dismantling_v3.get('configuration',{}).get('values',{})
    configuration_changes={k:{'previous':old_values.get(k),'proposed':value} for k,value in generated['configuration']['values'].items() if old_values.get(k)!=value}
    from app.services.dismantling_catalog import scoped_catalogue_digest
    local_sha=scoped_catalogue_digest(db,v.account_id,v)
    report=dict(local_catalogue_sha=local_sha,trial_input=trial_input,configuration_source_id=source_id,catalogue_revision=(db.get(CatalogueState,1).revision if db.get(CatalogueState,1) else None),configuration_changes=configuration_changes,version=VERSION,vehicle_id=v.id,configuration=generated['configuration'],catalogue_snapshot=generated['snapshot_sha'],catalogue_status=dict(published=generated['published'],fallback_used=generated['fallback_used']),proposals=proposals,differences=diffs,retained_historical_ids=retained,counts=dict(proposed=len(proposals),existing=counts['link'],new=counts['new'],review=counts['review'],skipped=counts['skip'],legacy_possible=sum(bool(p['candidates']) for p in proposals),unverified=sum(p['item']['applicability_status']!='confirmed' for p in proposals),with_stock_history=sum(protected(r) for r in existing)),etag=state(db,v,existing),archived=v.archived)
    report['token']=digest([who.actor_id,who.session.token_hash,data.model_dump(mode='json'),report])
    return report

def replay(db,v,who,data,kind):
    key=str(data.request_key);sha=digest([kind,v.id,who.actor_id,data.model_dump(mode='json')])
    old=db.scalar(select(DismantlingRequest).where(DismantlingRequest.account_id==v.account_id,DismantlingRequest.request_key==key))
    if old:
        if old.actor_id!=who.actor_id or old.vehicle_id!=v.id or old.request_sha!=sha:raise HTTPException(409,'Ключ запиту вже використано для іншої дії')
        return old.result,sha
    return None,sha
def finish(db,v,who,data,sha,result):
    db.add(DismantlingRequest(account_id=v.account_id,vehicle_id=v.id,actor_id=who.actor_id,request_key=str(data.request_key),request_sha=sha,result=result));db.flush();return result

def save(db,v,who,data):
    previous,sha=replay(db,v,who,data,'save')
    if previous:return previous
    if not data.confirm:raise HTTPException(422,'Потрібне явне підтвердження створення/оновлення плану')
    plan=make_preview(db,v,who,PlanPreview.model_validate(data.model_dump(exclude={'token','request_key','confirm'})))
    if data.token!=plan['token']:raise HTTPException(409,'Preview застарів; повторіть перевірку різниці')
    if plan['counts']['review']:raise HTTPException(409,'Спочатку вирішіть неоднозначні legacy-зіставлення')
    return persist_plan(db,v,who,data,plan,sha)

def partial_plan(plan,existing):
    """Defer entire uncertain components; never manufacture skip decisions.

    Graph edges: generic/refined overlaps and shared possible legacy rows.
    Previously bound exact identities remain present; no deferred row is created.
    Explicit reviewed distinct identities may coexist; target collisions never may.
    """
    proposals=plan['proposals'];by_id={p['id']:p for p in proposals};by_row={r.id:r for r in existing}
    active={p['id'] for p in proposals if p['action']!='skip'}
    links={pid:set() for pid in active};owners=defaultdict(list)
    def accepted(p):
        r=by_row.get(p['target_id'])
        return p['manual'] or bool(r and r.plan_v3.get('placement_id')==p['id'] and r.plan_v3.get('mapping_reason'))
    def edge(a,b):
        if a in active and b in active and a!=b:links[a].add(b);links[b].add(a)
    for p in proposals:
        if p['id'] not in active:continue
        for other in p['overlap_ids']:
            q=by_id[other]
            # Both physical identities explicitly reviewed; automatic generation
            # never supplies either of these decisions/reasons.
            if not (accepted(p) and accepted(q) and p['action']!='review' and q['action']!='review'):edge(p['id'],other)
        for target in {c['id'] for c in p['candidates']}|({p['target_id']} if p['target_id'] else set()):owners[target].append(p)
    for related in owners.values():
        # Uncertain candidates can still refer to a row claimed by an exact link.
        if any(p['action']=='review' for p in related) or len([p for p in related if p['target_id']])>1:
            first=related[0]['id']
            for p in related[1:]:edge(first,p['id'])
    uncertain={p['id'] for p in proposals if p['action']=='review'}
    for pid,neighbors in links.items():
        if neighbors:uncertain.add(pid)  # Conservatively defer unresolved overlap groups, even if tagged new/link.
    deferred=set();todo=list(uncertain)
    while todo:
        pid=todo.pop()
        if pid in deferred:continue
        deferred.add(pid);todo.extend(links.get(pid,()))
    pending=[];safe=[]
    for p in proposals:
        item=p['item'];a=item.get('applicability',{})
        variants=item.get('variants',[])
        contrary=item['applicability_status']=='incompatible' or bool(a.get('conflicting_fields')) or bool(variants and all(v.get('applicability',{}).get('conflicting_fields') for v in variants))
        reason=None
        if p['id'] in deferred:reason=p.get('conflict') or ('Є кілька можливих збігів з існуючими деталями' if p['candidates'] else 'Позиції можуть означати одну фізичну деталь')
        if p['action']=='new' and contrary:reason='Кандидат суперечить відомим характеристикам; потрібне уточнення комплектації'
        if reason:
            r=by_row.get(p['target_id'])
            # Keep an established exact identity untouched; only unresolved
            # additions belong in pending. Its historic decisions remain usable.
            if p['action']=='link' and r:
                safe.append(p)  # Proven unique identity: reuse only, never create another overlapping row.
                continue
            pending.append(dict(id=p['id'],name=item['name'],category=item['category'],subcategory=item['subcategory'],
                installation_position=item['installation_position'],reason=reason,candidates=p['candidates'],overlap_ids=p['overlap_ids'],
                needs='Уточніть комплектацію або перевірте фізичну тотожність та позицію; можна повернутися пізніше',status='pending_review'))
            continue
        safe.append(p)
    return {**plan,'proposals':safe},pending


def quick(db,v,who,data):
    previous,sha=replay(db,v,who,data,'quick')
    if previous is not None:return previous
    if state(db,v)!=data.etag:raise HTTPException(409,'Автомобіль, план або склад змінився. Оновіть список і повторіть дію')
    payload=PlanPreview.model_validate(data.model_dump(exclude={'etag','request_key','confirm','token'}))
    plan=make_preview(db,v,who,payload)
    if not plan['catalogue_status']['published']:raise HTTPException(409,'Конструктивний каталог ще не опубліковано власником платформи. План не створено; 33 базові позиції не є повним каталогом')
    if not plan['proposals']:raise HTTPException(409,'У каталозі немає кандидатів для цього автомобіля. План не змінено')
    if data.token is not None and data.token!=plan['token']:raise HTTPException(409,'Перевірка рішень застаріла; перечитайте актуальні відповідності')
    selected,pending=partial_plan(plan,rows_for(db,v))
    return persist_plan(db,v,who,data,selected,sha,partial=True,pending=pending)


def persist_plan(db,v,who,data,plan,sha,*,partial=False,pending=None):
    previous_vehicle=snapshot(v);revision=v.dismantling_v3.get('revision',0)+1;existing={r.id:r for r in rows_for(db,v)};counts=Counter();changes=[]
    for proposal in plan['proposals']:
        if proposal['action'] not in ('new','link'):continue
        item=proposal['item'];target=proposal['target_id'];r=existing.get(target)
        if r is None:
            pos=item['installation_position'];position=' '.join({'front':'передня','rear':'задня','left':'ліва','right':'права'}.get(pos[k],'') for k in ('position','side')).strip()
            r=DismantlingItem(id=sid('donor-plan',v.account_id,v.id,item['id'],str(data.request_key)),account_id=v.account_id,vehicle_id=v.id,source='carpot.v3',catalog_key=sid('plan-source',v.id,item['id'],str(data.request_key)),name=item['name'],position=position,category_key=sid('category',item['category']),category_name=item['category'],subcategory_key=sid('subcategory',item['category'],item['subcategory']),subcategory_name=item['subcategory'],included=True,status='unchecked',quantity=1,plan_v3={})
            db.add(r);counts['created']+=1;before={}
        else:before=snapshot(r);counts['linked' if not r.plan_v3 else 'updated']+=1
        r.plan_v3={**r.plan_v3,'placement_id':item['id'],'canonical_part_type_id':item['canonical_part_type_id'],'inspection':inspection(r),'reason':r.plan_v3.get('reason','' if r.included else 'Збережене виключення legacy'),'snapshot':item,'mapping_reason':proposal['reason'] if proposal['manual'] else r.plan_v3.get('mapping_reason',''),'mapping_decision':proposal['action'] if proposal['manual'] else r.plan_v3.get('mapping_decision'),'revision':revision}
        changes.append((r,before))
    skipped=dict(v.dismantling_v3.get('skipped',{}))
    for p in plan['proposals']:
        if p['action']=='skip':skipped[p['id']]=p['reason']
        elif p['action'] in ('new','link'):skipped.pop(p['id'],None)
    drafts={**v.dismantling_v3.get('review_drafts',{}),**{pid:r.model_dump() for pid,r in data.resolutions.items()}}
    pending_ids={p['id'] for p in (pending or [])}
    drafts={pid:r for pid,r in drafts.items() if pid in pending_ids}
    v.dismantling_v3={**v.dismantling_v3,**dict(trial_input=plan['trial_input'],configuration_source_id=plan['configuration_source_id'],vehicle_basis=basis(v),catalogue_revision=plan['catalogue_revision'],skipped=skipped,version=VERSION,revision=revision,configuration=plan['configuration'],catalogue_snapshot=plan['catalogue_snapshot'],local_catalogue_sha=plan['local_catalogue_sha'],preview_token=plan['token']), 'pending_review':pending if partial else [],'review_drafts':drafts}
    db.flush() # One batch assigns defaults and validates rows before audit snapshots.
    with db.no_autoflush:
        for r,before in changes:record(db,v.account_id,r,'dismantling_v3_bind','Підтверджено зіставлення/оновлення довідника; рішення і склад не змінено',before,flush_before=False)
        record(db,v.account_id,v,'dismantling_v3_save','Явно збережено індивідуальний план без оприбуткування',previous_vehicle,flush_before=False)
    result=dict(saved=True,revision=revision,**counts)
    if partial:result.update(created=counts['created'],reused=counts['linked']+counts['updated'],pending=len(pending),candidates=plan['counts']['proposed'],received=0)
    return finish(db,v,who,data,sha,result)

def decide(db,v,who,data):
    previous,sha=replay(db,v,who,data,'decision')
    if previous:return previous
    rows=rows_for(db,v)
    if state(db,v,rows)!=data.etag:raise HTTPException(409,'План або склад змінився; оновіть список')
    wanted=set(data.ids);targets=[r for r in rows if r.id in wanted]
    if len(targets)!=len(data.ids):raise HTTPException(404,'Позицію власного плану не знайдено')
    if any(not r.plan_v3 for r in targets):raise HTTPException(409,'Спочатку зіставте legacy-позицію через preview')
    if data.action!='receipt' and any(protected(r) for r in targets):raise HTTPException(409,'Позиція має складську історію; змінюйте її через складський workflow')
    if data.action in ('dismantled','receipt') and any(not r.included or inspection(r)!='present' or (data.action=='receipt' and r.status!='dismantled') for r in targets):raise HTTPException(409,'Спочатку підтвердіть наявність, потім демонтаж; лише тоді можливе оприбуткування')
    updated=apply_decisions(db,v,targets,data)
    return finish(db,v,who,data,sha,dict(updated=updated,total=len(targets)))


def apply_decisions(db,v,targets,data):
    updated=0;changes=[]
    for r in targets:
        before=snapshot(r)
        if data.action=='receipt':
            from app.services.dismantling import receipt
            updated+=int(receipt(db,r,SimpleNamespace(quantity=data.quantity,condition=data.condition,location=data.location,selling_price=None),v.account_id));continue
        meta=dict(r.plan_v3)
        if data.action=='dismantled':r.status='dismantled'
        elif data.action=='exclude':r.included=False;meta['reason']=data.reason
        elif data.action=='restore':
            r.included=True;meta['inspection']='unchecked' if inspection(r) in ('absent','not_applicable') else inspection(r);meta['reason']=''
        else:
            meta['inspection']=data.action;meta['inspection_source']='user_decision';r.included=data.action not in ('absent','not_applicable');meta['reason']=data.reason
            if data.action!='present':r.status='unchecked'
        r.plan_v3=meta
        if before!=snapshot(r):changes.append((r,before));updated+=1
    if changes:
        db.flush()
        with db.no_autoflush:
            for r,before in changes:record(db,v.account_id,r,'dismantling_v3_decision',data.reason or 'Явне рішення перевірки/демонтажу; без зміни залишку',before,flush_before=False)
    return updated
