"""Explicit constructive *plan* adoption. Never creates stock or physical membership.

Source reference rows remain distinct from actual attached AssemblyMembership edges.
No paid provider calls, no guess about factory configuration or physical presence.
"""
import re
from fastapi import HTTPException
from sqlalchemy import select
from app.models import DismantlingItem, Vehicle, AssemblyMembership, Part
from app.services.inventory import owned, record

SOURCE='carpot.assembly.door-reference.v1'
COMPONENTS={
    'shell':'Каркас дверей',
    'glass':'Скло дверей',
    'regulator':'Склопідіймач',
    'lock':'Замок дверей',
    'outer-handle':'Зовнішня ручка дверей',
    'inner-handle':'Внутрішня ручка дверей',
    'trim':'Обшивка дверей',
    'harness':'Проводка дверей',
    'seal':'Ущільнювач дверей',
}


def _axis(text,positive,negative,positive_value,negative_value):
    yes=bool(re.search(positive,text,re.I))
    no=bool(re.search(negative,text,re.I))
    return positive_value if yes and not no else negative_value if no and not yes else None


def door_axes(parent):
    """A conflicting or unknown source installation is never assumed to match."""
    label=(parent.position or '').casefold()
    from_label={
        'position':_axis(label,r'передн|front',r'задн|rear','front','rear'),
        'side':_axis(label,r'лів|left',r'прав|right','left','right'),
    }
    installation=((parent.plan_v3 or {}).get('snapshot') or {}).get('installation_position') or {}
    axes={}
    for key in ('position','side'):
        from_source=installation.get(key)
        from_source=from_source if from_source in (('front','rear') if key=='position' else ('left','right')) else None
        if from_source and from_label[key] and from_source!=from_label[key]:
            raise HTTPException(409,'Установчі характеристики дверей суперечливі; уточніть автомобіль')
        axes[key]=from_source or from_label[key]
    if not all(axes.values()):
        raise HTTPException(409,'Спочатку вкажіть точне розташування дверей: передні/задні та ліві/праві')
    return axes


def add_plan_component(db,account,vehicle_id,parent_id,key):
    v=owned(db,Vehicle,vehicle_id,account,lock=True,active=True)
    parent=owned(db,DismantlingItem,parent_id,account)
    if parent.vehicle_id!=v.id or parent.name.strip().casefold()!='двері':
        raise HTTPException(409,'Компонент можна додати лише до конкретних дверей цього автомобіля')
    if parent.assembly_consumed_operation_id or parent.status=='absent':
        raise HTTPException(409,'Двері відсутні або вже передані; план не змінено')
    if parent.part_id:
        stock=owned(db,Part,parent.part_id,account)
        if stock.vehicle_id!=v.id or stock.archived or stock.quantity!=1:
            raise HTTPException(409,'Двері продані, архівовані або мають неоднозначний фізичний залишок')
    if key not in COMPONENTS:raise HTTPException(422,'Невідомий компонент конструктивного шаблону')
    axes=door_axes(parent)
    label=COMPONENTS[key]
    catalog_key=f'door:{parent.id}:{key}'
    existing=list(db.scalars(select(DismantlingItem).where(
        DismantlingItem.account_id==account,DismantlingItem.vehicle_id==v.id
    ).order_by(DismantlingItem.id)))
    physical_parents={row.child_item_id:row.parent_item_id for row in db.scalars(select(AssemblyMembership).where(
        AssemblyMembership.account_id==account,AssemblyMembership.vehicle_id==v.id,AssemblyMembership.active.is_(True)
    ))}
    for item in existing:
        if item.source==SOURCE and item.catalog_key==catalog_key:
            return dict(created=False,item_id=item.id,name=item.name,part_id=item.part_id)
    # An existing plan row of the same exact name and installation is reused;
    # it is not silently added to physical membership or overwritten.
    for item in existing:
        if item.name.strip().casefold()!=label.casefold():continue
        try:
            other=door_axes(item)
        except HTTPException:
            continue
        if other==axes:
            if physical_parents.get(item.id) not in (None,parent.id):
                raise HTTPException(409,'Компонент уже належить іншому фізичному вузлу; перевірте існуючий запис')
            return dict(created=False,item_id=item.id,name=item.name,part_id=item.part_id)
    if len(existing)>=10000:raise HTTPException(409,'План перевищує межу фізичних позицій')
    position=' '.join((
        'передня' if axes['position']=='front' else 'задня',
        'ліва' if axes['side']=='left' else 'права',
    ))
    row=DismantlingItem(
        account_id=account,vehicle_id=v.id,source=SOURCE,catalog_key=catalog_key,
        category_key=parent.category_key,category_name=parent.category_name,
        subcategory_key='door-components',subcategory_name='Компоненти дверей',
        name=label,position=position,included=True,status='unchecked',quantity=1,
        plan_v3={
            'placement_id':f'door-template:{parent.id}:{key}',
            'assembly_reference_parent_id':parent.id,
            'assembly_template_key':key,
            'assembly_template_version':1,
            'inspection':'unchecked',
            'reason':'Додано до плану користувачем; фізична наявність і застосовність не підтверджені',
            'snapshot':{
                'installation_position':{**axes,'details':{'mount':[]}},
                'source_confirmed':False,
                'applicability_status':'unknown',
                'source':[{'kind':'carpot_constructive_reference','version':1}],
            },
        },
    )
    db.add(row);db.flush()
    record(db,account,row,'assembly_component_plan','Користувач додав типовий компонент до плану без складського надходження',{})
    return dict(created=True,item_id=row.id,name=row.name,part_id=None)
