"""Bounded bulk commands over the existing Part/Operation ledger.

Each command is atomic for its eligible subset. No ineligible row is mutated.
More than 1000 IDs must be explicit, checkpointed client batches.
"""
from collections import Counter
from types import SimpleNamespace
from fastapi import HTTPException
from app.services import dismantling_plan_v3 as plan
from app.services.catalogue_format import digest
ACTIONS=('present','absent','not_applicable','unchecked','exclude','restore','dismantled','receipt')


def eligibility(row,archived=False):
    blocked={a:None for a in ACTIONS}
    common='Архівовано' if archived else 'Уже оприбутковано; використайте складські операції' if plan.protected(row) else 'Потрібне зіставлення з планом' if not row.plan_v3.get('placement_id') else None
    if common:return {a:common for a in ACTIONS}
    if not row.included:
        for a in ACTIONS:
            if a!='restore':blocked[a]='Виключено з плану; спочатку поверніть'
        return blocked
    blocked['restore']='Уже включено до плану'
    present=plan.inspection(row)=='present'
    if present:blocked['present']='Наявність уже підтверджено'
    if not present:
        blocked['dismantled']='Спочатку підтвердіть наявність на автомобілі'
        blocked['receipt']='Наявність на автомобілі не підтверджена'
    elif row.status!='dismantled':blocked['receipt']='Потрібен фактичний демонтаж'
    if row.status=='dismantled':blocked['dismantled']='Уже демонтовано'
    return blocked


def preview(db,v,ids,action):
    rows=plan.rows_for(db,v);by_id={r.id:r for r in rows}
    if not set(ids)<=by_id.keys():raise HTTPException(404,'Позицію власного плану не знайдено')
    from app.models import Part
    from sqlalchemy import select
    archived=set(db.scalars(select(Part.id).where(Part.account_id==v.account_id,Part.vehicle_id==v.id,Part.archived.is_(True))))
    eligible=[];blocked=[];items=[]
    for id in ids:
        r=by_id[id];reason=eligibility(r,v.archived or r.part_id in archived)[action]
        (blocked if reason else eligible).append(dict(id=id,name=r.name,reason=reason) if reason else id)
        items.append(dict(id=id,name=r.name,position=r.position,included=r.included,inspection=plan.inspection(r),dismantled=r.status=='dismantled',received=bool(r.received_at),reason=reason))
    result=dict(action=action,selected=len(ids),eligible_ids=eligible,eligible=len(eligible),blocked=blocked,items=items,
        confirmed=sum(plan.inspection(by_id[id])=='present' for id in ids),dismantled=sum(by_id[id].status=='dismantled' for id in ids),received=sum(bool(by_id[id].received_at) for id in ids),etag=plan.state(db,v,rows))
    result['preview_token']=digest(result)
    return result


def select_ids(db,v,*,q='',category='',subcategory='',status='all',offset=0,limit=1000):
    listing=plan.listing(db,v)
    def matches(i):
        return (not category or i['category']==category) and (not subcategory or i['subcategory']==subcategory) and (not q or q.casefold() in (i['name']+' '+i['position']).casefold()) and (status=='all' or status=='excluded' and not i['included'] or status in (i['inspection'],i['operational_state']) or status=='app:'+i['applicability'])
    matched=[i for i in listing['items'] if matches(i)];available=[i['id'] for i in matched if i['selectable']]
    return dict(ids=available[offset:offset+limit],total=len(matched),available=len(available),offset=offset,limit=limit,etag=listing['etag'])


def execute(db,v,who,data):
    cached,sha=plan.replay(db,v,who,data,'bulk')
    if cached is not None:return cached
    report=preview(db,v,data.ids,data.action)
    if data.etag!=report['etag']:raise HTTPException(409,'План або склад змінився. Оновіть придатність перед наступною дією')
    if data.action=='receipt' and data.preview_token!=report['preview_token']:raise HTTPException(409,'Перевірка надходження застаріла; перегляньте підсумок')
    targets={r.id:r for r in plan.rows_for(db,v)};eligible=report['eligible_ids'];part_ids=[]
    if data.action=='receipt':
        lines={r.id:r for r in data.lines}
        if not set(eligible)<=lines.keys():raise HTTPException(409,'Для нових придатних позицій не підтверджено кількість. Перевірте підсумок знову')
        from app.services.dismantling import receipt
        updated=0
        for id in eligible:
            line=lines[id];r=targets[id]
            updated+=int(receipt(db,r,SimpleNamespace(quantity=line.quantity,condition=line.condition,location=line.location,selling_price=line.selling_price),v.account_id))
            part_ids.append(r.part_id)
    else:
        updated=plan.apply_decisions(db,v,[targets[id] for id in eligible],SimpleNamespace(action=data.action,reason=data.reason))
    result=dict(updated=updated,selected=len(data.ids),eligible=len(eligible),skipped=len(report['blocked']),blocked=report['blocked'],part_ids=part_ids,atomic=True,etag=plan.state(db,v))
    return plan.finish(db,v,who,data,sha,result)
