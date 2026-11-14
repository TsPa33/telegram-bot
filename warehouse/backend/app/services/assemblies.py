"""Physical graph policy for the existing Part/Operation/Order ledger."""
import hashlib
import json
import os
from contextlib import contextmanager
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select, or_
from app.models import Account, AssemblyMembership, AssemblyTemplate, DismantlingItem, DismantlingRequest, Operation, Part, Vehicle, now
from app.services.inventory import owned, record, snapshot


def enabled():
    return os.getenv('ASSEMBLY_INVENTORY_ENABLED','false').lower()=='true'


def lock_workspace(db,account):
    db.scalar(select(Account).where(Account.id==account).with_for_update(key_share=True))


def graph(db,account,vehicle,*,lock=False):
    if lock:
        lock_workspace(db,account)
        owned(db,Vehicle,vehicle,account,lock=True,active=True)
    query=select(DismantlingItem).where(DismantlingItem.account_id==account,DismantlingItem.vehicle_id==vehicle).order_by(DismantlingItem.id)
    nodes={n.id:n for n in db.scalars(query.with_for_update() if lock else query)}
    if len(nodes)>10000:raise HTTPException(409,'План перевищує межу 10000 фізичних позицій')
    edges=list(db.scalars(select(AssemblyMembership).where(AssemblyMembership.account_id==account,AssemblyMembership.vehicle_id==vehicle,AssemblyMembership.active).order_by(AssemblyMembership.id)))
    query=select(Part).where(Part.account_id==account,Part.id.in_([n.part_id for n in nodes.values() if n.part_id])).order_by(Part.id)
    parts={p.id:p for p in db.scalars(query.with_for_update() if lock else query)}
    return nodes,edges,parts


def closure(root,edges):
    result=[];pending=[root];seen=set()
    children={}
    for e in edges:children.setdefault(e.parent_item_id,[]).append(e.child_item_id)
    while pending:
        node=pending.pop()
        if node in seen:raise HTTPException(409,'Цикл у фізичному складі')
        seen.add(node);result.append(node);pending.extend(children.get(node,[]))
    return sorted(result)


def ancestors(node,edges):
    parents={e.child_item_id:e.parent_item_id for e in edges};result=[]
    while node in parents:
        node=parents[node]
        if node in result:raise HTTPException(409,'Цикл у фізичному складі')
        result.append(node)
    return result


def digest(data):
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def inspection_issues(node,part):
    issues=[]
    if node.status=='absent' or (part and part.availability=='absent' and not node.assembly_consumed_operation_id):issues.append('absent')
    if node.status=='damaged' or (part.condition if part else node.condition)=='damaged' or (part and part.availability=='damaged'):issues.append('damaged')
    if part and part.archived:issues.append('archived')
    return issues


def composition(nodes,edges,parts,root):
    ids=closure(root,edges)
    if root not in nodes:raise HTTPException(404,'Позицію не знайдено')
    rows=[dict(item_id=id,part_id=nodes[id].part_id,name=nodes[id].name,
        archived=parts[nodes[id].part_id].archived if nodes[id].part_id in parts else False,presence=nodes[id].status,availability=parts[nodes[id].part_id].availability if nodes[id].part_id in parts else None,condition=parts[nodes[id].part_id].condition if nodes[id].part_id in parts else nodes[id].condition,
        inspection=nodes[id].plan_v3.get('inspection'),note=nodes[id].plan_v3.get('inspection_note',''),planned_quantity=nodes[id].quantity,completeness=nodes[id].assembly_completeness,consumed_operation_id=nodes[id].assembly_consumed_operation_id,
        quantity=parts[nodes[id].part_id].quantity if nodes[id].part_id in parts else None) for id in ids]
    memberships=[dict(id=e.id,parent=e.parent_item_id,child=e.child_item_id) for e in edges if e.parent_item_id in ids]
    data=dict(root=root,items=rows,memberships=memberships)
    issues=[dict(item_id=id,name=nodes[id].name,reason=reason) for id in ids for reason in inspection_issues(nodes[id],parts.get(nodes[id].part_id))]
    return dict(**data,token=digest(data),issues=issues,incomplete=bool(issues) or any(nodes[id].assembly_completeness in ('unchecked','incomplete') for id in ids),
        conflicts=[dict(part_id=p.id,reserved=p.reserved_quantity) for p in parts.values() if p.id in {nodes[id].part_id for id in ids} and p.reserved_quantity])


def reservation_orders(db,account,part_ids):
    from app.models import OrderReservation,OrderLine,Order
    return [dict(order_id=order_id,order_number=number,part_id=r.part_id,quantity=r.quantity)
        for r,order_id,number in db.execute(select(OrderReservation,Order.id,Order.number)
        .join(OrderLine,OrderLine.id==OrderReservation.order_line_id).join(Order,Order.id==OrderLine.order_id)
        .where(OrderReservation.account_id==account,Order.account_id==account,OrderReservation.state=='active',OrderReservation.part_id.in_(part_ids)))]


def physically_missing(db,account,vehicle,root,edges):
    """Previously attached components not currently inside this root.

    Historical detaches cannot be overridden by marking the remainder 'complete'.
    A genuine, recorded re-attach restores completeness eligibility.
    """
    active=set(closure(root,edges))
    missing=list(db.scalars(select(AssemblyMembership).where(
        AssemblyMembership.account_id==account,
        AssemblyMembership.vehicle_id==vehicle,
        AssemblyMembership.parent_item_id.in_(active),
        AssemblyMembership.active.is_(False),
    )))
    return sorted({e.child_item_id for e in missing if e.child_item_id not in active})


def preview(db,account,item):
    node=owned(db,DismantlingItem,item,account)
    nodes,edges,parts=graph(db,account,node.vehicle_id)
    result=composition(nodes,edges,parts,item)
    missing=physically_missing(db,account,node.vehicle_id,item,edges)
    if missing:
        result['incomplete']=True
        result['missing_component_ids']=missing
    relevant=set(closure(item,edges)+ancestors(item,edges))
    result['reservation_orders']=reservation_orders(db,account,[nodes[id].part_id for id in relevant if nodes[id].part_id])
    return result


def tree(db,account,vehicle):
    v=owned(db,Vehicle,vehicle,account)
    refs=(v.dismantling_v3 or {}).get('volvo_oem_references',{})
    basis=None
    if refs:
        from app.services.dismantling_plan_v3 import generator_basis
        from app.services.volvo_oem_review import reference_matches
        basis=generator_basis(v)
    nodes,edges,parts=graph(db,account,vehicle)
    attached={e.child_item_id:e.parent_item_id for e in edges}
    consumed_types={op.id:op.type for op in db.scalars(select(Operation).where(Operation.account_id==account,Operation.id.in_([n.assembly_consumed_operation_id for n in nodes.values() if n.assembly_consumed_operation_id])))}
    last_stock={}
    for op in db.scalars(select(Operation).where(Operation.account_id==account,Operation.part_id.in_([p.id for p in parts.values() if p.quantity==0]),Operation.type.in_(['sale','write_off','receipt','correction','virtual_activation'])).distinct(Operation.part_id).order_by(Operation.part_id,Operation.created_at.desc(),Operation.id.desc())):
        last_stock[op.part_id]=op.type
    parents={e.child_item_id:e.parent_item_id for e in edges}
    affected=set()
    for n in nodes.values():
        if inspection_issues(n,parts.get(n.part_id)):
            current=n.id
            while current not in affected:
                affected.add(current)
                if current not in parents:break
                current=parents[current]
    assembly_parents={e.parent_item_id for e in edges}
    items=[]
    for n in nodes.values():
        p=parts.get(n.part_id)
        ref=refs.get(n.id)
        from app.services.auto_oem import options,valid_reference
        valid=bool(ref and valid_reference(v,n,ref)) if refs else False
        oem_view=dict(stock_oem=p.oem_number if p else '',reference_oem=ref['oem_number'] if valid else '',reference_oem_stale=bool(ref and not valid),oem_options=options(p.oem_provenance) if p and p.oem_number else options(ref) if valid else [])
        items.append(dict(**oem_view,id=n.id,name=n.name,position=n.position or '',installation_position=(n.plan_v3 or {}).get('snapshot',{}).get('installation_position') or {},placement_id=(n.plan_v3 or {}).get('placement_id'),plan_parent_id=(n.plan_v3 or {}).get('assembly_reference_parent_id'),category=n.category_name,subcategory=n.subcategory_name,parent_id=attached.get(n.id),part_id=n.part_id,
            completeness='incomplete' if n.id in affected and (n.assembly_completeness is not None or n.id in assembly_parents) else n.assembly_completeness,consumed_operation_id=n.assembly_consumed_operation_id,consumed_type=consumed_types.get(n.assembly_consumed_operation_id) or (last_stock.get(p.id) if p and p.quantity==0 and n.id not in attached else None),
            presence='absent' if 'absent' in inspection_issues(n,p) else 'damaged' if 'damaged' in inspection_issues(n,p) else 'present' if n.part_id or n.status=='dismantled' else n.plan_v3.get('inspection','unchecked'),condition=p.condition if p else n.condition,note=n.plan_v3.get('inspection_note',''),planned_quantity=n.quantity,individually_tracked=bool(p and p.individually_tracked),archived=bool(p and p.archived),quantity=p.quantity if p else 0,reserved=p.reserved_quantity if p else 0,
            standalone=bool(p and p.available_quantity>0 and p.assortment_enabled and not p.archived and n.id not in attached and not n.assembly_consumed_operation_id)))
    unlinked=list(db.scalars(select(Part).where(Part.account_id==account,Part.vehicle_id==vehicle,Part.archived.is_(False),Part.quantity==1,Part.reserved_quantity==0,~select(DismantlingItem.id).where(DismantlingItem.part_id==Part.id).exists()).order_by(Part.name,Part.id).limit(1000)))
    return dict(items=items,unlinked_parts=[{'id':p.id,'name':p.name} for p in unlinked],counts=dict(potential=len(nodes),confirmed_attached=sum('absent' not in inspection_issues(nodes[e.child_item_id],parts.get(nodes[e.child_item_id].part_id)) for e in edges),
        standalone=sum(i['standalone'] for i in items),included_in_sale=sum(bool(i['consumed_type']=='sale' and i['parent_id']) for i in items)))


def no_reserves(db,nodes,parts,ids):
    for id in ids:
        n=nodes[id];p=parts.get(n.part_id)
        if 'absent' in inspection_issues(n,p):raise HTTPException(409,'Компонент позначено відсутнім; спочатку звірте наявність')
        if n.assembly_consumed_operation_id:raise HTTPException(409,'Позиція вже передана у складі вузла; потрібне контрольоване повернення')
        if p and (p.archived or p.reserved_quantity):
            raise HTTPException(409,dict(message='Позиція архівована або має резерв; зніміть його у відповідному замовленні',part_id=p.id,orders=reservation_orders(db,p.account_id,[p.id])))


def internal_stock(db,part,kind,quantity,account,reason):
    from app.services.inventory import stock
    return stock(db,part,SimpleNamespace(type=kind,quantity=quantity,reason=reason,sale_price=None),account,
        return_operation=True,_assembly_internal=True)


def attach(db,account,vehicle,parent,child):
    nodes,edges,parts=graph(db,account,vehicle,lock=True)
    if parent not in nodes or child not in nodes:raise HTTPException(404,'Позицію цього донора не знайдено')
    if parent==child or parent in closure(child,edges):raise HTTPException(409,'Цикл заборонений')
    if any(e.child_item_id==child for e in edges):raise HTTPException(409,'Компонент уже має активного батька')
    pending=[(child,0)];height=0
    while pending:
        current,depth=pending.pop();height=max(height,depth)
        pending.extend((e.child_item_id,depth+1) for e in edges if e.parent_item_id==current)
    if len(ancestors(parent,edges))+1+height>32:raise HTTPException(409,'Максимальна глибина вузлів — 32 рівні')
    group=set(closure(child,edges)+[parent]+ancestors(parent,edges))
    no_reserves(db,nodes,parts,group)
    top=(ancestors(parent,edges) or [parent])[-1]
    root_part=parts.get(nodes[top].part_id)
    if not root_part or root_part.quantity!=1:raise HTTPException(409,'Спочатку підтвердіть одну фізичну одиницю кореневого вузла')
    for id in group:
        n=nodes[id];p=parts.get(n.part_id)
        if n.quantity!=1 or n.status=='absent' or not n.included or (p and (p.vehicle_id!=vehicle or p.quantity>1)):
            raise HTTPException(409,'Потрібна одна підтверджена фізична позиція того самого донора')
    c=nodes[child];p=parts.get(c.part_id)
    if p and p.quantity!=1:raise HTTPException(409,'Немає самостійної фізичної одиниці компонента. Спочатку оформіть контрольоване повернення.')
    if p and p.unit_cost is not None and p.unit_cost>0:raise HTTPException(409,'Компонент має власну собівартість. Узгодьте розподіл вартості перед включенням у вузол.')
    for id in group:
        physical=parts.get(nodes[id].part_id)
        if physical and not physical.individually_tracked:
            before_tracking=snapshot(physical);physical.individually_tracked=True
            record(db,account,physical,'assembly_identity','Закріплено індивідуальну фізичну ідентичність',before_tracking)
    if p and p.quantity:
        internal_stock(db,p,'assembly_containment',0,account,'Включено фізичну одиницю у вузол; не списання і не продаж')
    before=snapshot(c)
    for id in [parent]+ancestors(parent,edges):nodes[id].assembly_completeness='unchecked'
    op=record(db,account,c,'assembly_attach','Явно підтверджено фізичний склад',before,after_extra={'parent_item_id':parent})
    db.flush()
    db.add(AssemblyMembership(account_id=account,vehicle_id=vehicle,parent_item_id=parent,child_item_id=child,attached_operation_id=op.id))
    db.flush()
    return dict(attached=True)


def detach(db,account,vehicle,child):
    nodes,edges,parts=graph(db,account,vehicle,lock=True)
    edge=next((e for e in edges if e.child_item_id==child),None)
    if not edge:raise HTTPException(409,'Компонент не входить до вузла')
    no_reserves(db,nodes,parts,set(closure(child,edges)+ancestors(child,edges)))
    c=nodes[child];p=parts.get(c.part_id)
    if p and p.quantity:raise HTTPException(409,'Компонент уже має самостійний залишок')
    if not p:
        p=Part(account_id=account,vehicle_id=vehicle,name=c.name,quantity=0,reserved_quantity=0,individually_tracked=True,condition=c.condition or 'unknown')
        db.add(p);db.flush();c.part_id=p.id
    before=snapshot(c)
    op=internal_stock(db,p,'receipt',1,account,'Відокремлено підтверджений компонент вузла')
    db.flush();edge.active=False;edge.detached_at=now();edge.detached_operation_id=op.id
    c.received_at=c.received_at or now();c.status='dismantled'
    c.plan_v3={**(c.plan_v3 or {}),'assembly_reference_parent_id':edge.parent_item_id}
    for id in ancestors(child,edges):nodes[id].assembly_completeness='incomplete'
    record(db,account,c,'assembly_detach','Збережено історичний зв’язок із вузлом',before,after_extra={'former_parent_id':edge.parent_item_id})
    return dict(detached=True,part_id=p.id)


def confirm(db,account,vehicle,item,token):
    nodes,edges,parts=graph(db,account,vehicle,lock=True)
    if item not in nodes:raise HTTPException(404,'Позицію не знайдено')
    view=composition(nodes,edges,parts,item)
    if token!=view['token']:raise HTTPException(409,'Склад змінився; перегляньте його повторно')
    if view['issues']:raise HTTPException(409,'Є відсутні, пошкоджені або архівовані компоненти; повний комплект не підтверджено')
    if physically_missing(db,account,vehicle,item,edges):
        raise HTTPException(409,'Із вузла вже відокремлено компоненти. Продайте решту з точним описом або фізично приєднайте їх назад.')
    if any(e.child_item_id==item for e in edges):raise HTTPException(409,'Підтверджуйте склад від кореня або відокремте вузол')
    no_reserves(db,nodes,parts,closure(item,edges))
    if not parts.get(nodes[item].part_id) or parts[nodes[item].part_id].quantity!=1:raise HTTPException(409,'Немає фізичного кореневого вузла')
    before=snapshot(nodes[item])
    for id in closure(item,edges):
        if id==item or nodes[id].assembly_completeness is not None:nodes[id].assembly_completeness='complete'
    record(db,account,nodes[item],'assembly_confirm','Явно підтверджено поточну комплектність, не заводську BOM',before,after_extra={'composition':view})
    return dict(confirmed=True)


def stock_guard(db,part,data,account,confirmation=None):
    """Called for EVERY existing stock path, regardless of UI feature flag."""
    if part.id in db.info.get('fresh_unassembled_receipts',()):
        # IDs minted and inserted by this transaction cannot have committed assembly links.
        if data.type!='receipt' or part.quantity or part.reserved_quantity:raise HTTPException(409,'Invalid fresh receipt scope')
        return None
    lock_workspace(db,account)
    node=db.scalar(select(DismantlingItem).where(DismantlingItem.account_id==account,DismantlingItem.part_id==part.id))
    if node is None:return None
    membership_history=db.scalar(select(AssemblyMembership.id).where(AssemblyMembership.account_id==account,or_(AssemblyMembership.parent_item_id==node.id,AssemblyMembership.child_item_id==node.id)).limit(1))
    if data.type in ('sale','reserve') and 'absent' in inspection_issues(node,part):raise HTTPException(409,'Спочатку звірте наявність деталі')
    if node.assembly_completeness is None and not node.assembly_consumed_operation_id and not membership_history and node.source!='carpot.assembly.v1':return None
    nodes,edges,parts=graph(db,account,node.vehicle_id,lock=True)
    if any(e.child_item_id==node.id for e in edges):raise HTTPException(409,'Деталь входить до вузла. Спочатку відокремте її.')
    if node.assembly_consumed_operation_id:
        raise HTTPException(409,'Вузол уже передано; надходження можливе лише через контрольоване повернення')
    is_assembly=node.assembly_completeness is not None or any(e.parent_item_id==node.id for e in edges)
    if data.type in ('receipt','virtual_activation','correction'):
        raise HTTPException(409,'Фізичний ID не відновлюється корекцією або повторним надходженням; використайте контрольоване повернення')
    if not is_assembly:
        if data.type in ('sale','write_off','reserve'):
            if data.quantity!=1:raise HTTPException(409,'Один фізичний компонент — одна одиниця')
            view=composition(nodes,edges,parts,node.id)
            token=(confirmation or {}).get('token') or getattr(data,'assembly_token',None)
            if token and token!=view['token']:raise HTTPException(409,'Склад змінився; оновіть перегляд')
            if data.type!='write_off' and any(i['reason']=='absent' for i in view['issues']):raise HTTPException(409,'Фізичний компонент позначено відсутнім')
            return dict(view=view,description='',consume=data.type in ('sale','write_off'))
        return None
    if data.type in ('sale','write_off','reserve'):
        view=composition(nodes,edges,parts,node.id)
        missing=physically_missing(db,account,node.vehicle_id,node.id,edges)
        if missing:
            view['incomplete']=True
            view['missing_component_ids']=missing
        context=confirmation or dict(token=getattr(data,'assembly_token',None),description=getattr(data,'assembly_description',''),remainder=getattr(data,'assembly_remainder',False))
        if context.get('token')!=view['token']:raise HTTPException(409,'Спочатку перегляньте та підтвердіть фактичний склад вузла')
        description=context.get('description') or ''
        if view['incomplete'] and (not context.get('remainder') or len(description.strip())<5 or any(label in ' '.join(description.lower().split()) for label in ('в зборі','у зборі'))):
            raise HTTPException(409,'Неповний комплект: підтвердіть продаж решти та точний опис без «в зборі»')
        if data.quantity!=1:raise HTTPException(409,'Фізичний вузол продається або резервується як одна одиниця')
        for id in closure(node.id,edges):
            if 'absent' in inspection_issues(nodes[id],parts.get(nodes[id].part_id)):raise HTTPException(409,'Перевірка позначає компонент відсутнім. Звірте фізичний склад перед продажем.')
            p=parts.get(nodes[id].part_id)
            if id!=node.id and p and (p.quantity or p.reserved_quantity or p.archived):raise HTTPException(409,'Конфлікт складського стану компонента')
        return dict(view=view,description=description,consume=data.type in ('sale','write_off'))
    return None


def consumed(db,part,operation,context,account):
    if not context or not context['consume']:return
    from app.models import uid
    view=context['view']
    operation.id=operation.id or uid()
    operation.after={**operation.after,'assembly':dict(**view,description=context['description'])}
    db.flush()
    node_ids=[r['item_id'] for r in view['items']]
    nodes=list(db.scalars(select(DismantlingItem).where(DismantlingItem.account_id==account,DismantlingItem.id.in_(node_ids)).order_by(DismantlingItem.id)))
    order_id=(operation.after.get('sale') or {}).get('order_id')
    physical_parts={p.id:p for p in db.scalars(select(Part).where(Part.account_id==account,Part.id.in_([n.part_id for n in nodes if n.part_id])).order_by(Part.id))}
    for n in nodes:
        before=snapshot(n);n.assembly_consumed_operation_id=operation.id
        if n.part_id!=part.id:
            target=physical_parts[n.part_id] if n.part_id else n
            record(db,account,target,'assembly_included_'+operation.type,'Передано фактичний компонент без окремої виручки',snapshot(target) if n.part_id else before,
                after_extra={'assembly_node':snapshot(n),'included_in_sale':operation.type=='sale','parent_part_id':part.id,'parent_name':part.name,'order_number':(operation.after.get('sale') or {}).get('order_number'),'order_id':order_id,'root_sale_operation_id':operation.id},flush_before=False)


def inventory_return(db,account,vehicle,operation_id):
    operation=owned(db,Operation,operation_id,account)
    view=(operation.after or {}).get('assembly')
    if operation.type!='sale' or operation.vehicle_id!=vehicle or not view:raise HTTPException(409,'Немає snapshot продажу вузла')
    if db.scalar(select(Operation.id).where(Operation.account_id==account,Operation.type=='assembly_return',Operation.entity_id==operation.id)):
        raise HTTPException(409,'Повернення вже виконано')
    nodes,edges,parts=graph(db,account,vehicle,lock=True)
    ids=[r['item_id'] for r in view['items']]
    if any(id not in nodes or nodes[id].assembly_consumed_operation_id!=operation.id for id in ids):raise HTTPException(409,'Склад проданого вузла змінився')
    if {e.id for e in edges if e.parent_item_id in ids}!={e['id'] for e in view['memberships']}:raise HTTPException(409,'Історичний склад не збігається')
    for row in view['items']:
        p=parts.get(nodes[row['item_id']].part_id)
        if nodes[row['item_id']].part_id!=row['part_id'] or (p and (p.quantity or p.reserved_quantity or p.archived)):raise HTTPException(409,'Складські позиції змінилися')
    root=parts.get(operation.part_id)
    if not root:raise HTTPException(409,'Кореневу складську позицію не знайдено')
    receipt=internal_stock(db,root,'receipt',1,account,'Контрольоване повернення вузла; без автоматичного повернення коштів')
    db.flush()
    for id in ids:nodes[id].assembly_consumed_operation_id=None
    event=Operation(account_id=account,actor_id=db.info.get('actor_id',account),vehicle_id=vehicle,part_id=root.id,
        entity_id=operation.id,entity_type='operations',type='assembly_return',reason='Повернення майна, не грошова операція',
        before={'sale_operation_id':operation.id},after={'composition':view,'receipt_operation_id':receipt.id,'financial_refund':False})
    db.add(event)
    return dict(returned=True,financial_refund=False)


def command(db,who,vehicle,kind,data,execute):
    account=who.workspace_account_id;lock_workspace(db,account)
    payload=data.model_dump(mode='json',exclude={'request_key'})
    # Keep existing command fingerprints stable across this additive API extension.
    if kind!='assembly:inspect':
        for field in ('presence','quantity','note'):payload.pop(field,None)
    if kind!='assembly:receipt_bulk':payload.pop('include_damaged',None)
    sha=digest(dict(vehicle=vehicle,kind=kind,data=payload))
    prior=db.scalar(select(DismantlingRequest).where(DismantlingRequest.account_id==account,DismantlingRequest.request_key==str(data.request_key)))
    if prior:
        if prior.actor_id!=who.actor_id or prior.request_sha!=sha:raise HTTPException(409,'Ключ уже використано для іншої дії або виконавця')
        return prior.result
    owned(db,Vehicle,vehicle,account,lock=True,active=True)
    result=execute()
    db.add(DismantlingRequest(account_id=account,actor_id=who.actor_id,vehicle_id=vehicle,request_key=str(data.request_key),request_sha=sha,result=result))
    db.commit();return result


def protect_identity(db,part,new_vehicle):
    node=db.scalar(select(DismantlingItem).where(DismantlingItem.account_id==part.account_id,DismantlingItem.part_id==part.id))
    if node and new_vehicle!=part.vehicle_id and (node.assembly_completeness is not None or node.assembly_consumed_operation_id or db.scalar(select(AssemblyMembership.id).where(AssemblyMembership.child_item_id==node.id))):
        raise HTTPException(409,'Фізичний компонент вузла не переноситься між донорами')


def assert_uncontained_item(db,node,account):
    lock_workspace(db,account)
    if node.assembly_consumed_operation_id or db.scalar(select(AssemblyMembership.id).where(AssemblyMembership.account_id==account,AssemblyMembership.child_item_id==node.id,AssemblyMembership.active)):
        raise HTTPException(409,'Компонент фізично входить у вузол; спочатку відокремте його')


def save_template(db,account,data):
    from app.models.canonical import CanonicalPlacement
    payload=data.template
    nodes=payload.get('placements',[]);edges=payload.get('edges',[])
    if len(json.dumps(payload,ensure_ascii=False).encode())>512*1024:raise HTTPException(422,'Шаблон перевищує 512 КіБ')
    if not isinstance(nodes,list) or any(not isinstance(n,str) or not 1<=len(n)<=36 for n in nodes):raise HTTPException(422,'Некоректні каталожні ідентифікатори')
    if not isinstance(nodes,list) or not 1<=len(nodes)<=10000 or len(set(nodes))!=len(nodes) or not isinstance(edges,list) or len(edges)>10000:
        raise HTTPException(422,'Некоректний шаблон')
    known=set(db.scalars(select(CanonicalPlacement.id).where(CanonicalPlacement.id.in_(nodes))))
    if known!=set(nodes):raise HTTPException(422,'Шаблон має посилатися на чинні каталожні установчі позиції')
    parents={}
    for edge in edges:
        if not isinstance(edge,dict) or edge.get('parent') not in known or edge.get('child') not in known or edge['child'] in parents or edge.get('quantity',1)!=1:
            raise HTTPException(422,'Неправильний зв’язок або фізичну кількість не розділено на окремі позиції')
        parents[edge['child']]=edge['parent']
    for node in nodes:
        seen=set();cursor=node
        while cursor in parents:
            cursor=parents[cursor]
            if cursor==node or cursor in seen or len(seen)>=32:raise HTTPException(422,'Цикл або завелика глибина шаблону')
            seen.add(cursor)
    old=db.scalar(select(AssemblyTemplate).where(AssemblyTemplate.account_id==account,AssemblyTemplate.name==data.name,AssemblyTemplate.version==data.version))
    if old:
        if old.payload!=payload or old.provenance!=data.provenance:raise HTTPException(409,'Версія шаблону незмінна')
        return dict(template_id=old.id)
    row=AssemblyTemplate(account_id=account,name=data.name,version=data.version,payload=payload,provenance=data.provenance)
    db.add(row);db.flush()
    return dict(template_id=row.id)


def receive_root(db,account,vehicle,item,token='',_graph=None):
    """Explicit receipt via the existing ledger; assemblies remain single physical IDs."""
    from app.services import dismantling,unified_catalogue
    from app.api.dismantling import DismantlingAction
    nodes,edges,parts=_graph or graph(db,account,vehicle,lock=True)
    if item not in nodes:raise HTTPException(404,'Позицію не знайдено')
    n=nodes[item];assert_uncontained_item(db,n,account)
    if token and token!=composition(nodes,edges,parts,item)['token']:raise HTTPException(409,'Дані деталі змінилися. Оновіть перевірку перед надходженням.')
    if n.part_id:
        raise HTTPException(409,'Позицію вже пов’язано зі складом; повторне надходження через вузли заборонене')
    if n.source=='carpot.catalogue.v1':
        v=owned(db,Vehicle,vehicle,account)
        state=unified_catalogue.saved_state(v)
        if not state or unified_catalogue.needs_review(v):raise HTTPException(409,'Потрібна звірка збереженого каталогу')
        product=next((r for r in state['payload']['categories'] if n.catalog_key==f"car:{state['payload']['car_id']}:product:{r['product_id']}"),None)
        if not product or product.get('kind')!='part':raise HTTPException(409,'Неперевірені типи, обладнання й витратні матеріали потребують окремих правил')
    if n.quantity!=1 and (n.assembly_completeness is not None or any(e.parent_item_id==item or e.child_item_id==item for e in edges)):raise HTTPException(409,'Один фізичний вузол — одна одиниця')
    if n.status=='absent' or n.plan_v3.get('inspection')!='present':raise HTTPException(409,'Спочатку підтвердьте наявність деталі на автомобілі')
    before=snapshot(n);n.status='dismantled'
    record(db,account,n,'dismantling_status','Підтверджено демонтаж перед додаванням на склад',before)
    dismantling.actions(db,vehicle,account,DismantlingAction(ids=[item],action='receipt',quantity=n.quantity))
    return dict(received=True,part_id=n.part_id)


def link_existing_part(db,account,vehicle,part_id):
    """Explicit adoption of a legacy/manual/Plan.Parts physical ID, no backfill."""
    part=owned(db,Part,part_id,account,lock=True,active=True)
    if part.vehicle_id!=vehicle or part.quantity!=1 or part.reserved_quantity:
        raise HTTPException(409,'Потрібна одна незарезервована фізична позиція цього донора')
    existing=db.scalar(select(DismantlingItem).where(DismantlingItem.part_id==part.id,DismantlingItem.account_id==account))
    if existing:return dict(item_id=existing.id,created=False)
    from app.models import Category
    categories={c.id:c.name for c in db.scalars(select(Category).where(Category.account_id==account,Category.id.in_([part.category_id,part.subcategory_id])))}
    node=DismantlingItem(account_id=account,vehicle_id=vehicle,part_id=part.id,source='carpot.assembly.v1',catalog_key='part:'+part.id,
        category_key=part.category_id or 'unclassified',category_name=categories.get(part.category_id,'Потребує уточнення'),subcategory_key=part.subcategory_id or 'unclassified',subcategory_name=categories.get(part.subcategory_id,'Потребує уточнення'),
        name=part.name,quantity=1,status='dismantled',received_at=now(),plan_v3={'origin':'explicit_existing_part_link'})
    if not part.individually_tracked:
        before=snapshot(part);part.individually_tracked=True
        record(db,account,part,'assembly_identity','Закріплено один фізичний ID без зміни кількості',before)
    db.add(node);db.flush()
    record(db,account,node,'assembly_part_link','Явно пов’язано існуючий фізичний ID; залишок не змінено',{},after_extra={'part_id':part.id})
    return dict(item_id=node.id,created=True)


def part_context(db,account,part_id):
    node=db.scalar(select(DismantlingItem).where(DismantlingItem.account_id==account,DismantlingItem.part_id==part_id))
    if not node:return None
    parent=db.scalar(select(AssemblyMembership).where(AssemblyMembership.account_id==account,AssemblyMembership.child_item_id==node.id,AssemblyMembership.active))
    if node.assembly_consumed_operation_id:
        op=owned(db,Operation,node.assembly_consumed_operation_id,account)
        return dict(state=('sold_separately' if node.assembly_completeness is None and len((op.after.get('assembly') or {}).get('items',[]))==1 else 'sold_in_assembly') if op.type=='sale' else 'written_off_in_assembly',parent_name=(op.after.get('assembly') or {}).get('description') or op.after.get('name'),
            order_id=(op.after.get('sale') or {}).get('order_id'),order_number=(op.after.get('sale') or {}).get('order_number'),vehicle_id=node.vehicle_id)
    if parent:
        p=owned(db,DismantlingItem,parent.parent_item_id,account)
        return dict(state='contained',parent_name=p.name,vehicle_id=node.vehicle_id)
    return None


def managed_part(db,part):
    node=db.scalar(select(DismantlingItem).where(DismantlingItem.account_id==part.account_id,DismantlingItem.part_id==part.id))
    return bool(node and (node.assembly_completeness is not None or node.assembly_consumed_operation_id or node.source=='carpot.assembly.v1' or db.scalar(select(AssemblyMembership.id).where(AssemblyMembership.account_id==part.account_id,or_(AssemblyMembership.parent_item_id==node.id,AssemblyMembership.child_item_id==node.id)).limit(1))))


def inspect_item(db,account,vehicle,data):
    """Inspection is metadata, never a receipt; quantity lots use the sole stock ledger."""
    from app.services.inventory import stock
    nodes,edges,parts=graph(db,account,vehicle,lock=True)
    n=nodes.get(data.item_id)
    if not n:raise HTTPException(404,'Позицію цього автомобіля не знайдено')
    if composition(nodes,edges,parts,n.id)['token']!=data.token:raise HTTPException(409,'Дані деталі змінилися. Відкрийте її ще раз.')
    relevant=closure(n.id,edges)+ancestors(n.id,edges)
    if any(nodes[i].assembly_consumed_operation_id or (parts.get(nodes[i].part_id) and (parts[nodes[i].part_id].reserved_quantity or parts[nodes[i].part_id].archived)) for i in relevant):
        raise HTTPException(409,'Продана, архівована або зарезервована деталь недоступна для редагування')
    p=parts.get(n.part_id)
    if p and p.quantity==0:
        last=db.scalar(select(Operation).where(Operation.account_id==account,Operation.part_id==p.id,Operation.type.in_(['sale','write_off','receipt','correction','virtual_activation'])).order_by(Operation.created_at.desc(),Operation.id.desc()).limit(1))
        if last and last.type in ('sale','write_off'):raise HTTPException(409,'Цю позицію вже продано або списано; використайте чинний контрольований процес повернення')
    physical=bool(n.assembly_completeness is not None or any(e.child_item_id==n.id or e.parent_item_id==n.id for e in edges) or (p and p.individually_tracked))
    before=snapshot(n)
    current=p.quantity if p else n.quantity
    if data.quantity!=current:
        if physical:raise HTTPException(409,'Ця фізична деталь обліковується окремо; її кількість не можна дублювати')
        if p:
            stock(db,p,SimpleNamespace(type='correction',quantity=data.quantity,reason='Уточнення фактичної кількості під час перевірки автомобіля',sale_price=None),account)
        else:
            if data.quantity<1:raise HTTPException(422,'Для відсутньої деталі виберіть «Відсутня», не нульову кількість плану')
            n.quantity=data.quantity
    n.plan_v3={**n.plan_v3,'inspection':'present' if data.presence=='damaged' else data.presence,'inspection_source':'user_decision','inspection_note':data.note}
    n.status='damaged' if data.presence=='damaged' else 'absent' if data.presence=='absent' else 'dismantled' if n.received_at else 'unchecked'
    n.condition='damaged' if data.presence=='damaged' else 'used' if n.condition=='damaged' else n.condition
    if p:
        old=snapshot(p)
        p.condition='damaged' if data.presence=='damaged' else 'used' if p.condition=='damaged' else p.condition
        p.availability='absent' if data.presence=='absent' else 'damaged' if data.presence=='damaged' else 'present'
        record(db,account,p,'update','Перевірка наявності та стану; залишок не змінено',old)
    record(db,account,n,'dismantling_status','Збережено результат фізичної перевірки',before)
    return dict(saved=True,item_id=n.id)


def confirmed_receipt_preview(db,account,vehicle,include_damaged=False,*,locked_graph=None):
    """Read-only, pinned eligible subset; at most 100 receipts per atomic command."""
    from app.services import unified_catalogue
    v=owned(db,Vehicle,vehicle,account)
    nodes,edges,parts=locked_graph or graph(db,account,vehicle)
    state=unified_catalogue.saved_state(v)
    products={f"car:{state['payload']['car_id']}:product:{row['product_id']}":row.get('kind') for row in state['payload']['categories']} if state else {}
    catalogue_ready=bool(state and not unified_catalogue.needs_review(v))
    attached={e.child_item_id for e in edges}
    eligible=[];skipped=[];stamp=[]
    for n in sorted(nodes.values(),key=lambda n:n.id):
        p=parts.get(n.part_id)
        issues=inspection_issues(n,p)
        damaged='damaged' in issues
        confirmed=n.plan_v3.get('inspection')=='present'
        reason=None
        if v.archived:reason='Автомобіль архівовано'
        elif n.assembly_consumed_operation_id:reason='Продано або списано'
        elif n.id in attached:reason='У складі вузла'
        elif n.part_id or n.received_at:reason='Уже пов’язано зі складом'
        elif not n.included:reason='Виключено зі списку'
        elif 'absent' in issues:reason='Відсутня'
        elif not confirmed:reason='Спочатку підтвердьте наявність'
        elif damaged and not include_damaged:reason='Пошкоджена — потрібне окреме підтвердження'
        elif n.source=='carpot.catalogue.v1' and (not catalogue_ready or products.get(n.catalog_key)!='part'):reason='Потрібна перевірка каталожної позиції'
        elif n.quantity!=1 and (n.assembly_completeness is not None or any(e.parent_item_id==n.id for e in edges)):reason='Потрібна одна фізична одиниця вузла'
        elif len(eligible)>=100:reason='Наступний пакет — ліміт 100 позицій'
        row=dict(id=n.id,name=n.name,quantity=n.quantity,damaged=damaged)
        if reason:skipped.append({**row,'reason':reason})
        else:eligible.append(row)
        stamp.append(dict(id=n.id,part_id=n.part_id,received=bool(n.received_at),status=n.status,condition=n.condition,quantity=n.quantity,included=n.included,inspection=n.plan_v3.get('inspection'),note=n.plan_v3.get('inspection_note'),consumed=n.assembly_consumed_operation_id))
    report=dict(eligible=eligible,skipped=skipped,include_damaged=include_damaged,total=len(nodes),semantics='atomic',limit=100)
    report['token']=digest(dict(report=report,vehicle=vehicle,archived=v.archived,stamp=stamp,edges=[(e.id,e.parent_item_id,e.child_item_id) for e in edges],parts=[dict(id=p.id,quantity=p.quantity,reserved=p.reserved_quantity,archived=p.archived,condition=p.condition,availability=p.availability) for p in parts.values()]))
    return report


def receive_confirmed(db,account,vehicle,data):
    nodes,edges,parts=graph(db,account,vehicle,lock=True)
    report=confirmed_receipt_preview(db,account,vehicle,data.include_damaged,locked_graph=(nodes,edges,parts))
    if not data.token or report['token']!=data.token:raise HTTPException(409,'Список змінився. Перевірте підсумок надходження ще раз.')
    results=[]
    for row in report['eligible']:
        result=receive_root(db,account,vehicle,row['id'],_graph=(nodes,edges,parts))
        results.append(dict(item_id=row['id'],part_id=result['part_id'],name=row['name'],quantity=row['quantity']))
    return dict(received=results,skipped=report['skipped'],semantics='atomic')
