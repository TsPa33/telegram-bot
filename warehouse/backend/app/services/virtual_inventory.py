"""Virtual donor activation in the existing Part/Operation ledger only."""
from types import SimpleNamespace
from collections import defaultdict
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Account, Part, Operation, DismantlingRequest
from app.models.canonical import CanonicalPlacement
from app.services import dismantling_plan_v3 as plan
from app.services.inventory import record, snapshot, stock
from app.schemas.dismantling_v3 import PlanPreview


def lock_workspace(db, account_id):
    db.scalar(select(Account).where(Account.id==account_id).with_for_update(key_share=True))


def activate(db,v,who,data):
    old,sha=plan.replay(db,v,who,data,'virtual_activation')
    if old is not None:return old
    if plan.state(db,v)!=data.etag:raise HTTPException(409,'Автомобіль або склад змінився. Оновіть список')
    report=plan.make_preview(db,v,who,PlanPreview.model_validate(data.model_dump(exclude={'etag','request_key','confirm','token'})),virtual_base=True)
    if data.token and data.token!=report['token']:raise HTTPException(409,'Перевірка рішень застаріла')
    safe,pending=plan.partial_plan(report,plan.rows_for(db,v))
    result=plan.persist_plan(db,v,who,data,safe,sha,partial=True,pending=pending)
    placements=set(db.scalars(select(CanonicalPlacement.id)))
    activated=0;linked=0
    categories={};subcategories={}
    selected={p['item']['id'] for p in safe['proposals'] if p['action'] in ('new','link')}
    for row in plan.rows_for(db,v):
        placement=row.plan_v3.get('placement_id')
        if row.part_id and not row.included:
            existing=db.get(Part,row.part_id)
            if existing.assortment_enabled and not existing.archived:
                if existing.reserved_quantity:raise HTTPException(409,'Стара виключена позиція має активний резерв; узгодьте його перед переходом')
                previous=snapshot(existing);existing.assortment_enabled=False
                record(db,v.account_id,existing,'assortment_change','Збережено старе явне виключення при переході до віртуального обліку',previous)
        if placement not in selected or not row.included:continue
        if row.part_id:
            # Old receipts, sold/archived parts and user prices are authoritative.
            linked+=1;continue
        before=snapshot(row)
        from app.services.dismantling import category_node
        reason='Категорія віртуального обліку; без фізичного надходження'
        if row.category_key not in categories:
            categories[row.category_key]=category_node(db,v.account_id,row.source,'category:'+row.category_key,row.category_name,'category',reason=reason)
        root=categories[row.category_key]
        subkey=(root.id,row.subcategory_key)
        if subkey not in subcategories:
            subcategories[subkey]=category_node(db,v.account_id,row.source,'subcategory:'+row.category_key+':'+row.subcategory_key,row.subcategory_name,'subcategory',root.id,reason=reason)
        sub=subcategories[subkey]
        leaf=category_node(db,v.account_id,row.source,'part:'+row.catalog_key,row.name,'part',sub.id,reason=reason)
        # Receipt-created legacy Part reuse is resolved by the existing planner;
        # do not guess a second physical identity from a similar name.
        part=Part(account_id=v.account_id,vehicle_id=v.id,name=row.name+(' · '+row.position if row.position else ''),
            inventory_origin='virtual_donor',quantity_basis='assumed',physical_location_kind='on_vehicle',
            category_id=root.id,subcategory_id=sub.id,checklist_category_id=leaf.id,
            assortment_enabled=True,condition='unknown',quantity=0,reserved_quantity=0,
            canonical_placement_id=placement if placement in placements else None)
        db.add(part);db.flush()
        record(db,v.account_id,part,'part_create','Віртуальна облікова позиція; кількість ще не перевірена',{})
        op=stock(db,part,SimpleNamespace(type='virtual_activation',quantity=1,reason='Віртуальний облік: 1 як редаговане припущення',sale_price=None),v.account_id,return_operation=True)
        op.after={**op.after,'virtual':dict(snapshot=report['catalogue_snapshot'],placement_id=placement,
            configuration=report['configuration'],quantity_basis='assumed',request_key=str(data.request_key))}
        db.flush();part.activation_operation_id=op.id;row.part_id=part.id
        # received_at and physical inspection/status deliberately remain unchanged.
        record(db,v.account_id,row,'virtual_inventory_link','Пов’язано з єдиним складом без фізичного надходження',before)
        activated+=1
    v.dismantling_v3={**v.dismantling_v3,'inventory_mode':'virtual_v1','basic_coverage':not any(p['item'].get('relevant_offer_count',0) for p in report['proposals'])}
    result={**result,'activated':activated,'reused_parts':linked,'received':0,'basic_coverage':v.dismantling_v3['basic_coverage']}
    request=db.scalar(select(DismantlingRequest).where(DismantlingRequest.account_id==v.account_id,DismantlingRequest.request_key==str(data.request_key)))
    request.result=result
    return result


def listing(db,v):
    state=plan.listing(db,v)
    parts={p.id:p for p in db.scalars(select(Part).where(Part.account_id==v.account_id,Part.vehicle_id==v.id))}
    sold=defaultdict(int);other_decreases=set()
    for op in db.scalars(select(Operation).where(Operation.account_id==v.account_id,Operation.vehicle_id==v.id,Operation.type.in_(['sale','write_off','correction']))):
        before=(op.before or {}).get('quantity');after=(op.after or {}).get('quantity')
        if type(before) is int and type(after) is int and before>after:
            if op.type=='sale':sold[op.part_id]+=before-after
            else:other_decreases.add(op.part_id)
    donor_rows={r.id:r for r in plan.rows_for(db,v)}
    for item in state['items']:
        evidence=donor_rows[item['id']].plan_v3.get('snapshot',{})
        item['configuration_warning']=bool(evidence.get('applicability',{}).get('conflicting_fields')) or any(bool(v.get('applicability',{}).get('conflicting_fields')) for v in evidence.get('variants',[]))
        p=parts.get(item['part_id'])
        item.update(stock=None,selectable=bool(p and not p.archived and not v.archived))
        if p:
            item['included']=p.assortment_enabled and item['included']
            item['stock']=dict(id=p.id,quantity=p.quantity,reserved_quantity=p.reserved_quantity,available_quantity=p.available_quantity,
                sold_quantity=sold[p.id],assortment_enabled=p.assortment_enabled,archived=p.archived,condition=p.condition,
                location=p.location,physical_location_kind=p.physical_location_kind,quantity_basis=p.quantity_basis,
                selling_price=str(p.selling_price) if p.selling_price is not None else None,currency=p.currency,
                state='available' if p.available_quantity>0 else 'reserved' if p.quantity>0 else 'sold' if sold[p.id] and p.id not in other_decreases else None)
    state.update(virtual_mode=v.dismantling_v3.get('inventory_mode')=='virtual_v1',basic_coverage=v.dismantling_v3.get('basic_coverage',not state['catalogue_status']['published']))
    state['virtual_counts']=dict(active=sum(bool(i['stock'] and i['included'] and not i['stock']['archived'] and i['stock']['quantity']>0) for i in state['items']),
        excluded=sum(not i['included'] for i in state['items']),reserved=sum(bool(i['stock'] and i['stock']['reserved_quantity']) for i in state['items']),
        sold=sum(bool(i['stock'] and i['stock']['state']=='sold') for i in state['items']))
    return state


def availability(db,v,who,data):
    old,sha=plan.replay(db,v,who,data,'virtual_availability')
    if old is not None:return old
    if data.etag!=plan.state(db,v):raise HTTPException(409,'План або склад змінився. Оновіть список')
    rows=[r for r in plan.rows_for(db,v) if r.id in set(data.ids)]
    if len(rows)!=len(data.ids):raise HTTPException(404,'Позицію власного плану не знайдено')
    parts={p.id:p for p in db.scalars(select(Part).where(Part.account_id==v.account_id,Part.id.in_([r.part_id for r in rows])).order_by(Part.id).with_for_update())}
    for r in rows:
        p=parts.get(r.part_id)
        if not p or p.archived:raise HTTPException(409,'Немає активної складської позиції')
        if not data.enabled and p.reserved_quantity:raise HTTPException(409,'Спочатку зніміть резерв через замовлення або склад')
        if data.enabled and p.quantity==0:raise HTTPException(409,'Нульовий залишок: увімкнення не створює нової одиниці')
    count=0
    for r in rows:
        p=parts[r.part_id]
        if p.assortment_enabled==data.enabled:continue
        before=snapshot(p);rb=snapshot(r);p.assortment_enabled=data.enabled;r.included=data.enabled
        record(db,v.account_id,p,'assortment_change','Явна зміна доступності без зміни залишку',before)
        record(db,v.account_id,r,'virtual_availability','Синхронізовано доступність асортименту',rb);count+=1
    return plan.finish(db,v,who,data,sha,dict(updated=count))
