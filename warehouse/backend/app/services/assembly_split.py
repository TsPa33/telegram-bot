"""Explicit, atomic physical splitting of ONE stocked assembly into sellable parts.

A constructive reference is not inventory. Only user-confirmed physical separation
creates a DismantlingItem/Part, through existing assembly attach -> detach ledger.
Request replay, locks and commit are owned by assemblies.command.
"""
import json
import re
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.models import AssemblyMembership, DismantlingItem, Part
from app.services import assemblies
from app.services.inventory import record, snapshot

_CATALOG=json.loads((Path(__file__).resolve().parents[1]/'data/assembly_units_v1.json').read_text(encoding='utf-8'))
FAMILIES={u['id']:u for u in _CATALOG['units']}
SOURCE='carpot.assembly.split.v1'


def _normalized(value):
    result=' '.join(str(value or '').strip().casefold().split())
    return re.sub(r'\s+(?:у|в)\s+зборі$', '', result).strip()


def family_for(node):
    name=_normalized(node.name)
    for family in FAMILIES.values():
        if name in {_normalized(alias) for alias in family['aliases']}:
            return family
    return None


def _is_valid_root(db,account,vehicle,root_id,nodes,edges,parts):
    root=nodes.get(root_id)
    if root is None:raise HTTPException(404,'Вузол автомобіля не знайдено')
    if any(e.child_item_id==root_id for e in edges):
        raise HTTPException(409,'Відокремлення можливе лише від кореневого фізичного вузла')
    if root.assembly_consumed_operation_id or root.status=='absent' or not root.included:
        raise HTTPException(409,'Вузол уже передано, відсутній або виключений із плану')
    part=parts.get(root.part_id)
    if not part or part.vehicle_id!=vehicle or part.quantity!=1 or part.archived:
        raise HTTPException(409,'Для розбору потрібна одна активна фізична складська одиниця')
    if part.reserved_quantity or part.availability=='absent':
        raise HTTPException(409,'Вузол зарезервований або позначений відсутнім')
    assemblies.no_reserves(db,nodes,parts,assemblies.closure(root_id,edges))
    family=family_for(root)
    if family is None:raise HTTPException(409,'Цей тип вузла не має затвердженого конструктивного довідника')
    return root,part,family


def _history(db,account,vehicle,root_id):
    return list(db.scalars(select(AssemblyMembership).where(
        AssemblyMembership.account_id==account,
        AssemblyMembership.vehicle_id==vehicle,
        AssemblyMembership.parent_item_id==root_id,
    )))


def split(db,account,vehicle,root_id,unit_id,requested,token):
    nodes,edges,parts=assemblies.graph(db,account,vehicle,lock=True)
    root,root_part,family=_is_valid_root(db,account,vehicle,root_id,nodes,edges,parts)
    if unit_id!=family['id']:
        raise HTTPException(409,'Конструктивна модель вузла змінилася. Оновіть сторінку')
    current=assemblies.composition(nodes,edges,parts,root_id)
    if not token or token!=current['token']:
        raise HTTPException(409,'Склад або резерви змінилися. Оновіть перегляд вузла')
    if not requested or len(requested)>20:
        raise HTTPException(422,'Оберіть від 1 до 20 фізично відокремлених компонентів')
    indexes=[r.index for r in requested]
    if len(set(indexes))!=len(indexes) or any(i<0 or i>=len(family['parts']) for i in indexes):
        raise HTTPException(422,'Компонент відсутній у конструктивному довіднику або вибраний двічі')

    histories=_history(db,account,vehicle,root_id)
    active={edge.child_item_id:edge for edge in edges if edge.parent_item_id==root_id}
    detached_ids={e.child_item_id for e in histories if not e.active}
    done=[]
    original_root=snapshot(root)

    # All checks occur inside one locked, replay-protected transaction.
    # The same source component may never become two independent physical Parts.
    for selection in requested:
        label=family['parts'][selection.index]
        # Legacy stock may have no DismantlingItem. Reject creating a second
        # physical unit with the same identity until the operator reconciles it.
        standalone=list(db.scalars(select(Part).where(
            Part.account_id==account,Part.vehicle_id==vehicle,
            Part.id!=root_part.id,Part.quantity>0,Part.archived.is_(False)
        )))
        linked_stock={n.part_id:n for n in nodes.values() if n.part_id}
        if any(_normalized(p.name)==_normalized(label) and not (
            linked_stock.get(p.id) is not None and root.position and
            linked_stock[p.id].position and linked_stock[p.id].position!=root.position
        ) for p in standalone):
            raise HTTPException(409,f'«{label}» уже має активний залишок на цій установчій позиції. Звірте склад')
        existing=[n for n in nodes.values() if
            n.id!=root_id and _normalized(n.name)==_normalized(label)
            and (n.position==root.position or not n.position)
            and n.id not in detached_ids]
        attached=[n for n in existing if n.id in active]
        if len(attached)>1:raise HTTPException(409,'Вузол має кілька однакових компонентів; потрібна звірка')
        if any(n.id in detached_ids for n in nodes.values() if
            n.id!=root_id and _normalized(n.name)==_normalized(label)
            and ((n.plan_v3 or {}).get('assembly_reference_parent_id')==root_id
                 or n.source==SOURCE)):
            raise HTTPException(409,f'Компонент «{label}» уже відокремлено від вузла')

        if attached:
            child=attached[0]
            if child.part_id and parts[child.part_id].quantity:
                raise HTTPException(409,'Компонент уже має окремий складський залишок')
        else:
            # Do not claim a component as new if an independent stocked or
            # ambiguous plan position is already present for this same donor.
            other=[n for n in existing if n.part_id or
                (n.plan_v3 or {}).get('assembly_reference_parent_id') not in (None,root_id)]
            if other:
                raise HTTPException(409,f'«{label}» вже є в іншій фізичній або плановій позиції. Перевірте склад')
            reusable=[n for n in existing if
                (n.plan_v3 or {}).get('assembly_reference_parent_id')==root_id
                and not n.assembly_consumed_operation_id]
            if len(reusable)>1:
                raise HTTPException(409,f'Неоднозначні записи компонента «{label}»')
            if reusable:
                child=reusable[0]
                if child.status=='absent':raise HTTPException(409,f'«{label}» позначено відсутнім')
            else:
                if existing:raise HTTPException(409,f'«{label}» уже є в плані. Уточніть розташування перед відокремленням')
                key=f'{root_id}:{family["id"]}:{selection.index}'
                if any(n.source==SOURCE and n.catalog_key==key for n in nodes.values()):
                    raise HTTPException(409,f'«{label}» уже зареєстровано при попередньому розборі')
                child=DismantlingItem(
                    account_id=account,vehicle_id=vehicle,source=SOURCE,catalog_key=key,
                    category_key=root.category_key,category_name=root.category_name,
                    subcategory_key='assembly-components',subcategory_name='Складові вузла',
                    name=label,position=root.position or '',quantity=1,included=True,
                    status='unchecked',condition=selection.condition,
                    plan_v3={
                        'assembly_reference_parent_id':root_id,
                        'assembly_unit_id':family['id'],'assembly_component_index':selection.index,
                        'inspection':'present','inspection_source':'explicit_physical_dismantling',
                        'reason':'Користувач підтвердив фізичне відокремлення від конкретного вузла',
                        'snapshot':{'source_confirmed':False,'factory_bom':False},
                    },
                )
                db.add(child);db.flush()
            child.condition=selection.condition
            # This temporarily links the newly confirmed physical component
            # under the original single-stock root using the existing graph.
            assemblies.attach(db,account,vehicle,root_id,child.id)

        # Existing detach operation records both the physical history and
        # *one* receipt in the canonical Part/Operation ledger.
        result=assemblies.detach(db,account,vehicle,child.id)
        child.plan_v3={**(child.plan_v3 or {}),
            'assembly_reference_parent_id':root_id,'assembly_unit_id':family['id'],
            'assembly_component_index':selection.index,
            'inspection':'present','inspection_source':'explicit_physical_dismantling'}
        done.append({'item_id':child.id,'part_id':result['part_id'],
                     'name':child.name,'condition':selection.condition})

    # The parent remains an existing SKU, now an INCOMPLETE remainder,
    # never a second full assembly or a new stock receipt.
    root.assembly_completeness='incomplete'
    if not root_part.individually_tracked:root_part.individually_tracked=True
    record(db,account,root,'assembly_split_batch',
        'Фізично відокремлено складові; вузол залишився неповним',
        original_root,after_extra={
            'root_part_id':root_part.id,'family':family['id'],
            'separated':done,'root_quantity':root_part.quantity,
            'factory_bom':False,'cost_allocation':'not_automated',
        })
    return {'split':done,'count':len(done),'root_item_id':root.id,
            'root_part_id':root_part.id,'root_remaining_quantity':root_part.quantity,
            'root_completeness':'incomplete','cost_allocation':'not_automated'}
