"""PR5 isolated warehouse*_test PostgreSQL regression, NEVER staging/production."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.models import AssemblyMembership, DismantlingItem, Operation, Part, Vehicle
from app.services import assemblies


def key():
    return str(uuid4())


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv('ASSEMBLY_INVENTORY_ENABLED','true')


@pytest.fixture
def stocked(logged,vehicle):
    with Session(engine()) as db:
        account=db.get(Vehicle,vehicle['id']).account_id
        root_part=Part(account_id=account,vehicle_id=vehicle['id'],name='Двері',
            quantity=1,reserved_quantity=0,availability='present',condition='used',
            individually_tracked=True,unit_cost=Decimal('70.00'))
        db.add(root_part);db.flush()
        root=DismantlingItem(account_id=account,vehicle_id=vehicle['id'],
            part_id=root_part.id,source='pr5.synthetic',catalog_key='front-left-door',
            category_key='body',category_name='Кузов',subcategory_key='doors',
            subcategory_name='Двері',name='Двері',position='передня ліва',
            quantity=1,included=True,status='dismantled',condition='used',
            plan_v3={'inspection':'present'})
        db.add(root);db.flush();ids=dict(account=account,vehicle=vehicle['id'],
            root=root.id,root_part=root_part.id);db.commit()
    return ids


def preview(c,g):
    r=c.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies/{g['root']}/preview")
    assert r.status_code==200,r.text
    return r.json()


def split(c,g,indexes,**override):
    data=dict(request_key=key(),root_item_id=g['root'],unit_id='doors',
        token=preview(c,g)['token'],confirm_physical=True,
        components=[dict(index=i,condition='used') for i in indexes])
    data.update(override)
    return c.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies/split",json=data)


def sale(c,part,**override):
    data=dict(request_key=key(),type='sale',quantity=1,
        sale_price='155.00',sale_currency='UAH')
    data.update(override)
    return c.post(f"/api/v1/parts/{part}/operations",json=data)


def count(db,model):
    return db.scalar(select(func.count()).select_from(model))


def test_split_two_components_atomic_one_root_and_independent_sales(logged,stocked):
    g=stocked
    selected=[dict(index=1,condition='used'),dict(index=3,condition='damaged')]
    r=split(logged,g,[],components=selected)
    assert r.status_code==200,r.text
    result=r.json()
    assert result['count']==2 and result['root_part_id']==g['root_part']
    assert result['root_completeness']=='incomplete'
    glass,lock=result['split']
    assert glass['name']=='Скло дверей' and lock['name']=='Замок дверей'
    assert glass['part_id']!=lock['part_id']
    with Session(engine()) as db:
        assert count(db,Part)==3
        assert count(db,DismantlingItem)==3
        assert count(db,AssemblyMembership)==2
        memberships=list(db.scalars(select(AssemblyMembership)))
        assert all(not e.active and e.detached_at and e.detached_operation_id for e in memberships)
        assert db.get(Part,g['root_part']).quantity==1
        assert db.get(Part,g['root_part']).unit_cost==Decimal('70.00')
        assert db.get(DismantlingItem,g['root']).assembly_completeness=='incomplete'
        assert db.get(Part,glass['part_id']).quantity==1
        assert db.get(Part,lock['part_id']).quantity==1
        assert db.get(Part,lock['part_id']).condition=='damaged'
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==2
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='assembly_split_batch'))==1
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='sale'))==0
    state=preview(logged,g)
    assert state['incomplete'] is True and len(state['missing_component_ids'])==2
    assert logged.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=dict(
        request_key=key(),action='confirm',item_id=g['root'],token=state['token'],
        confirm_physical=True)).status_code==409
    full=sale(logged,g['root_part'],assembly_token=state['token'])
    assert full.status_code==409,full.text
    one=sale(logged,glass['part_id'])
    assert one.status_code==200,one.text
    remainder=sale(logged,g['root_part'],assembly_token=state['token'],
                   assembly_remainder=True,assembly_description='Двері без скла та замка')
    assert remainder.status_code==200,remainder.text
    with Session(engine()) as db:
        assert db.get(Part,glass['part_id']).quantity==0
        assert db.get(Part,g['root_part']).quantity==0
        assert db.get(Part,lock['part_id']).quantity==1
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='sale'))==2


def test_split_replay_duplicate_and_stale_token(logged,stocked):
    g=stocked;old=preview(logged,g)['token'];request=key()
    components=[dict(index=1,condition='used')]
    r=split(logged,g,[],components=components,token=old,request_key=request)
    assert r.status_code==200,r.text
    assert split(logged,g,[],components=components,token=old,request_key=request).json()==r.json()
    assert split(logged,g,[],components=components,token=old,request_key=request,
                 confirm_physical=False).status_code==422
    assert split(logged,g,[],components=[dict(index=1,condition='new')],token=old,
                 request_key=request).status_code==409
    assert split(logged,g,[],components=components,token=old).status_code==409
    assert split(logged,g,[1]).status_code==409
    with Session(engine()) as db:
        assert count(db,Part)==2
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1


def test_split_conflicts_invalid_selection_and_reserve(logged,stocked):
    g=stocked
    assert split(logged,g,[2,2]).status_code==422
    assert split(logged,g,[99]).status_code==422
    assert split(logged,g,[1],unit_id='engine').status_code==409
    with Session(engine()) as db:
        db.get(Part,g['root_part']).reserved_quantity=1
        db.commit()
    assert split(logged,g,[1]).status_code==409
    with Session(engine()) as db:
        assert count(db,Part)==1
        assert count(db,AssemblyMembership)==0


def test_split_reuses_previously_attached_child_and_preserves_id(logged,stocked):
    g=stocked
    with Session(engine()) as db:
        child=DismantlingItem(account_id=g['account'],vehicle_id=g['vehicle'],
            name='Скло дверей',position='передня ліва',source='synthetic.child',
            catalog_key='glass',category_key='body',category_name='Кузов',
            subcategory_key='glass',subcategory_name='Скло',quantity=1,status='unchecked')
        db.add(child);db.flush();child_id=child.id;db.commit()
    r=logged.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=dict(
        request_key=key(),action='attach',parent_id=g['root'],item_id=child_id,
        confirm_physical=True))
    assert r.status_code==200,r.text
    r=split(logged,g,[1])
    assert r.status_code==200,r.text
    assert r.json()['split'][0]['item_id']==child_id
    with Session(engine()) as db:
        assert count(db,DismantlingItem)==2
        assert count(db,Part)==2
        assert db.scalar(select(func.count()).select_from(AssemblyMembership).where(AssemblyMembership.active))==0


def test_split_reuses_legacy_plan_child_without_duplicating_plan(logged,stocked):
    g=stocked
    with Session(engine()) as db:
        n=DismantlingItem(account_id=g['account'],vehicle_id=g['vehicle'],
            name='Замок дверей',position='передня ліва',source='carpot.assembly.door-reference.v1',
            catalog_key='legacy-plan-lock',category_key='body',category_name='Кузов',
            subcategory_key='lock',subcategory_name='Замки',quantity=1,status='unchecked',
            plan_v3={'assembly_reference_parent_id':g['root'],'inspection':'unchecked'})
        db.add(n);db.flush();child_id=n.id;db.commit()
    r=split(logged,g,[3]);assert r.status_code==200,r.text
    assert r.json()['split'][0]['item_id']==child_id
    with Session(engine()) as db:assert count(db,DismantlingItem)==2


def test_atomic_rollback_if_second_detach_fails(logged,stocked,monkeypatch):
    g=stocked
    original=assemblies.detach;calls=[0]
    def fails_after_first(*args,**kwargs):
        calls[0]+=1
        if calls[0]==2:raise HTTPException(409,'Synthetic failure mid-batch')
        return original(*args,**kwargs)
    monkeypatch.setattr(assemblies,'detach',fails_after_first)
    result=split(logged,g,[1,3]);assert result.status_code==409,result.text
    with Session(engine()) as db:
        assert count(db,Part)==1
        assert count(db,DismantlingItem)==1
        assert count(db,AssemblyMembership)==0
        assert db.get(DismantlingItem,g['root']).assembly_completeness is None
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==0


def test_cross_donor_and_no_stock_root_cannot_split(logged,stocked):
    g=stocked
    second=logged.post('/api/v1/vehicles',json=dict(
        manufacturer='Test',model='Second',year=2020)).json()
    other=logged.post(f"/api/v1/vehicles/{second['id']}/assemblies/split",json=dict(
        request_key=key(),root_item_id=g['root'],unit_id='doors',
        components=[dict(index=1)],confirm_physical=True,token=preview(logged,g)['token']))
    assert other.status_code==404,other.text
    with Session(engine()) as db:
        db.get(Part,g['root_part']).quantity=0
        db.commit()
    assert split(logged,g,[1]).status_code==409


def test_single_root_reference_catalogue_preserves_24_family_ids():
    from app.services.assembly_split import FAMILIES
    assert len(FAMILIES)==24
    assert len({u['id'] for u in FAMILIES.values()})==24
    assert all(len(f['parts'])>=5 and f['aliases'] for f in FAMILIES.values())
    assert sum(len(f['parts']) for f in FAMILIES.values())==154
