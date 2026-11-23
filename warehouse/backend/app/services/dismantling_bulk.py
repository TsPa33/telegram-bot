"""Bounded bulk commands over the existing Part/Operation ledger.

Each command is atomic for its eligible subset. No ineligible row is mutated.
More than 1000 IDs must be explicit, checkpointed client batches.
"""
from collections import Counter
from types import SimpleNamespace
from fastapi import HTTPException
from app.services import dismantling_plan_v3 as plan
from app.services.catalogue_format import digest
from app.services.plan_item_binding import active_binding
from app.services import unified_catalogue as catalogue
ACTIONS=('present','absent','not_applicable','unchecked','exclude','restore','dismantled','receipt')


def source_receipt_eligible(vehicle, row, products=None):
    """Pinned source PRD types may be received ONLY after physical confirmation.

    A source association is not VIN fitment or a reviewed part classification.
    Never allow unbound, stale, excluded, sold, or protected rows.
    """
    if (row.source != 'carpot.catalogue.v1' or row.part_id or row.received_at
            or not row.included or row.status == 'absent' or vehicle.archived
            or (row.plan_v3 or {}).get('placement_id')):
        return False
    saved = catalogue.saved_state(vehicle)
    if not saved or catalogue.needs_review(vehicle):
        return False
    payload = saved.get('payload') or {}
    source_sha = payload.get('source_snapshot_sha')
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        return False
    product_id = catalogue.row_product_id(row)
    if product_id is None:
        return False
    if row.catalog_key != f"car:{payload.get('car_id')}:product:{product_id}":
        return False
    if products is None:
        products = {p['product_id']: p for p in payload.get('categories', [])}
    product = products.get(product_id)
    if not product or product.get('kind') not in ('part', 'review'):
        return False
    binding = active_binding(vehicle, row.id)
    return bool(binding and (
        binding.get('source_modification_id'),
        binding.get('product_id'),
        binding.get('snapshot_sha'),
        binding.get('manufacturer_id'),
    ) == (
        payload.get('car_id'), product_id, source_sha,
        payload.get('manufacturer_id'),
    ))


def eligibility(row,archived=False,source_receipt=False):
    blocked={a:None for a in ACTIONS}
    common='Архівовано' if archived else 'Уже оприбутковано; використайте складські операції' if plan.protected(row) else 'Потрібне зіставлення з планом' if not row.plan_v3.get('placement_id') and not source_receipt else None
    if common:return {a:common for a in ACTIONS}
    if not row.included:
        for a in ACTIONS:
            if a!='restore':blocked[a]='Виключено з плану; спочатку поверніть'
        return blocked
    blocked['restore']='Уже включено до плану'
    if source_receipt and not row.plan_v3.get('placement_id'):
        for action in ACTIONS:
            if action != 'receipt':
                blocked[action] = 'Це джерельна позиція: для інших дій потрібне зіставлення плану'
    present=plan.inspection(row)=='present'
    if present:blocked['present']='Наявність уже підтверджено'
    if not present:
        blocked['dismantled']='Спочатку підтвердіть наявність на автомобілі'
        blocked['receipt']='Наявність на автомобілі не підтверджена'
    # Receipt explicitly confirms both physical dismantling and stock intake.
    # In one transaction, execute() records dismantling before the existing receipt ledger.
    if row.status=='dismantled':blocked['dismantled']='Уже демонтовано'
    return blocked


def preview(db,v,ids,action,confirm_physical=False):
    rows=plan.rows_for(db,v);by_id={r.id:r for r in rows}
    payload=(catalogue.saved_state(v) or {}).get('payload') or {}
    products={p['product_id']:p for p in payload.get('categories',[])}
    if not set(ids)<=by_id.keys():raise HTTPException(404,'Позицію власного плану не знайдено')
    from app.models import Part
    from sqlalchemy import select
    archived=set(db.scalars(select(Part.id).where(Part.account_id==v.account_id,Part.vehicle_id==v.id,Part.archived.is_(True))))
    eligible=[];blocked=[];items=[]
    for id in ids:
        r=by_id[id]
        source_receipt=source_receipt_eligible(v,r,products)
        reason=eligibility(r,v.archived or r.part_id in archived,source_receipt)[action]
        needs_confirmation=plan.inspection(r)=='unchecked'
        if (action=='receipt' and confirm_physical and needs_confirmation
                and not plan.protected(r) and r.included and not v.archived
                and r.status != 'absent'
                and (r.plan_v3.get('placement_id') or source_receipt)):
            reason=None
        (blocked if reason else eligible).append(dict(id=id,name=r.name,reason=reason) if reason else id)
        items.append(dict(id=id,name=r.name,position=r.position,included=r.included,inspection=plan.inspection(r),dismantled=r.status=='dismantled',received=bool(r.received_at),reason=reason,requires_confirmation=needs_confirmation,quantity=r.quantity,condition=r.condition or ('damaged' if r.status=='damaged' else None)))
    result=dict(action=action,selected=len(ids),eligible_ids=eligible,eligible=len(eligible),blocked=blocked,items=items,
        confirmed=sum(plan.inspection(by_id[id])=='present' for id in ids),dismantled=sum(by_id[id].status=='dismantled' for id in ids),received=sum(bool(by_id[id].received_at) for id in ids),etag=plan.state(db,v,rows))
    if confirm_physical:result['confirm_physical']=True
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
    report=preview(db,v,data.ids,data.action,data.confirm_physical)
    if data.etag!=report['etag']:raise HTTPException(409,'План або склад змінився. Оновіть придатність перед наступною дією')
    if data.action=='receipt' and data.preview_token!=report['preview_token']:raise HTTPException(409,'Перевірка надходження застаріла; перегляньте підсумок')
    targets={r.id:r for r in plan.rows_for(db,v)};eligible=report['eligible_ids'];part_ids=[]
    if data.action=='receipt':
        lines={r.id:r for r in data.lines}
        if not set(eligible)<=lines.keys():raise HTTPException(409,'Для нових придатних позицій не підтверджено кількість. Перевірте підсумок знову')
        from app.services.dismantling import receipt
        from app.services.inventory import snapshot,record
        updated=0
        for id in eligible:
            line=lines[id];r=targets[id]
            if plan.inspection(r)=='unchecked':
                if not data.confirm_physical or not line.confirm_physical:
                    raise HTTPException(409,'Підтвердьте фактичну наявність і демонтаж кожної нової деталі')
                if r.plan_v3.get('placement_id'):
                    before=snapshot(r)
                    r.plan_v3={**r.plan_v3,'inspection':'present','inspection_source':'receipt_confirmation'}
                    record(db,v.account_id,r,'dismantling_v3_decision',
                           'Фактичну наявність підтверджено під час надходження',before)
                # Source-bound legacy items remain legacy rows, not artificial
                # v3 placements. The explicit receipt below proves physical intake.
            if r.status=='damaged' and r.condition is None:r.condition='damaged'
            # A receipt is an explicit user confirmation of actual dismantling.
            # Keep the same audit trail and transaction as the stock receipt.
            # Any failure rolls both changes back; no VIN-based auto-confirmation.
            if r.status!='dismantled':
                before=snapshot(r)
                r.status='dismantled'
                record(db,v.account_id,r,'dismantling_v3_decision','Фізичний демонтаж підтверджено разом із надходженням',before)
            updated+=int(receipt(db,r,SimpleNamespace(quantity=line.quantity,condition=line.condition,location=line.location,selling_price=line.selling_price),v.account_id))
            part_ids.append(r.part_id)
    else:
        updated=plan.apply_decisions(db,v,[targets[id] for id in eligible],SimpleNamespace(action=data.action,reason=data.reason))
    result=dict(updated=updated,selected=len(data.ids),eligible=len(eligible),skipped=len(report['blocked']),blocked=report['blocked'],part_ids=part_ids,atomic=True,etag=plan.state(db,v))
    return plan.finish(db,v,who,data,sha,result)
