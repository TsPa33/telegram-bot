"""Local workflow against dedicated PostgreSQL only, never a provider request."""
from concurrent.futures import ThreadPoolExecutor
from subprocess import run
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.db import engine
from app.models import DismantlingItem, Part, Operation
from app.api.dismantling import DismantlingAction
from app.services import dismantling
from conftest import signup


@pytest.fixture
def xc90(logged):
    result=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2010,'status':'planned'})
    assert result.status_code==201
    return result.json()


def path(vehicle):return '/api/v1/vehicles/'+vehicle['id']+'/dismantling'


def begin(client,vehicle):
    result=client.post(path(vehicle)+'/start')
    assert result.status_code==200,result.text
    return client.get(path(vehicle)).json()['items']


def act(client,vehicle,ids,action,**extra):
    return client.post(path(vehicle)+'/actions',json={'ids':ids,'action':action,**extra})


def test_start_without_ktype_is_idempotent_and_does_not_create_stock(logged,xc90,monkeypatch):
    monkeypatch.setenv('PLAN_PARTS_ENABLED','false')
    rows=begin(logged,xc90)
    assert len(rows)==33
    assert all(r['status']=='unchecked' and r['part_id'] is None and r['received_at'] is None for r in rows)
    assert xc90['ktype'] is None
    assert logged.get('/api/v1/vehicles/'+xc90['id']).json()['status']=='dismantling'
    assert logged.post(path(xc90)+'/start').json()['created']==0
    assert logged.get('/api/v1/parts').json()['total']==0
    with engine().connect() as db:
        assert db.execute(text('SELECT count(*) FROM categories')).scalar_one()==0
        assert db.execute(text("SELECT count(*) FROM operations WHERE type='dismantling_start'")).scalar_one()==1


def test_status_alone_then_receipt_existing_ledger_and_repeat(logged,xc90):
    row=begin(logged,xc90)[0]
    assert act(logged,xc90,[row['id']],'dismantled').status_code==200
    assert logged.get('/api/v1/parts').json()['total']==0
    result=act(logged,xc90,[row['id']],'receipt',quantity=1,condition='used',location='A-01',selling_price='1200')
    assert result.status_code==200 and result.json()['updated']==1
    part=logged.get('/api/v1/parts').json()['items'][0]
    assert part['vehicle_id']==xc90['id'] and part['quantity']==1 and part['reserved_quantity']==0
    assert part['location']=='A-01' and part['selling_price']=='1200.00'
    assert part['category_id'] and part['subcategory_id']
    assert act(logged,xc90,[row['id']],'receipt',quantity=99).json()['updated']==0
    assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==1
    audit=logged.get('/api/v1/audit?vehicle_id='+xc90['id']).json()['items']
    receipts=[r for r in audit if r['type']=='receipt']
    assert len(receipts)==1 and receipts[0]['before']['quantity']==0 and receipts[0]['after']['quantity']==1
    assert any(r['type']=='dismantling_receipt' for r in audit)
    assert act(logged,xc90,[row['id']],'absent').status_code==409


def test_bulk_mixed_retries_atomic_failure_and_damage(logged,xc90):
    rows=begin(logged,xc90)
    ids=[r['id'] for r in rows[:3]]
    act(logged,xc90,[ids[1]],'absent')
    assert act(logged,xc90,ids,'receipt').status_code==409
    assert logged.get('/api/v1/parts').json()['total']==0
    act(logged,xc90,[ids[1]],'damaged')
    act(logged,xc90,[ids[1]],'dismantled')
    assert act(logged,xc90,ids,'receipt',quantity=2).json()['updated']==3
    assert act(logged,xc90,ids,'receipt',quantity=2).json()['skipped']==3
    data=logged.get(path(xc90)).json()
    assert data['dismantled_positions']==3 and data['stock_positions']==3 and data['stock_units']==6
    damaged=next(row for row in data['items'] if row['id']==ids[1])
    assert damaged['stock']['condition']=='damaged'
    assert len([r for r in logged.get('/api/v1/audit?vehicle_id='+xc90['id']).json()['items'] if r['type']=='receipt'])==3


def test_concurrent_start_and_receipt_once(logged,xc90):
    def start(_):
        with Session(engine()) as db:
            result=dismantling.start(db,xc90['id'],xc90['account_id']);db.commit();return result['created']
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(start,range(2)))==33
    row=logged.get(path(xc90)).json()['items'][0]
    data=DismantlingAction(ids=[row['id']],action='receipt')
    def receipt(_):
        with Session(engine()) as db:
            result=dismantling.actions(db,xc90['id'],xc90['account_id'],data);db.commit();return result['updated']
    with ThreadPoolExecutor(max_workers=3) as pool:assert sum(pool.map(receipt,range(3)))==1
    assert logged.get('/api/v1/parts').json()['items'][0]['quantity']==1


def test_account_csrf_archiving_and_validation(logged,xc90):
    row=begin(logged,xc90)[0]
    with TestClient(app) as other:
        assert other.get(path(xc90)).status_code==401
        signup(other,'other-dismantling@example.test')
        assert other.get(path(xc90)).status_code==404
        assert other.post(path(xc90)+'/start').status_code==404
        assert act(other,xc90,[row['id']],'receipt').status_code==404
        own=other.post('/api/v1/vehicles',json={'manufacturer':'Other','model':'Own','year':2000}).json()
        assert act(other,own,[row['id']],'receipt').status_code==404
    assert act(logged,xc90,[row['id'],row['id']],'receipt').status_code==422
    for quantity in [0,-1,True,1.5]:
        assert act(logged,xc90,[row['id']],'receipt',quantity=quantity).status_code==422
    assert act(logged,xc90,[row['id']],'receipt',selling_price=-1).status_code==422
    csrf=logged.headers.pop('X-CSRF-Token')
    assert logged.post(path(xc90)+'/start').status_code==403
    assert act(logged,xc90,[row['id']],'receipt').status_code==403
    logged.headers['X-CSRF-Token']=csrf
    logged.post('/api/v1/archive/vehicles/'+xc90['id'])
    assert logged.get(path(xc90)).status_code==200
    assert logged.post(path(xc90)+'/start').status_code==404
    assert act(logged,xc90,[row['id']],'receipt').status_code==404


def test_existing_plan_parts_checklist_survives_start_and_edit(logged,xc90):
    from app.models import VehicleChecklistItem
    with Session(engine()) as db:
        provider=VehicleChecklistItem(account_id=xc90['account_id'],vehicle_id=xc90['id'],ktype=9743,
            pt_id=1,name_en='Mirror',name_uk='Дзеркало',article_count=100,status='present')
        db.add(provider);db.commit();provider_id=provider.id
    begin(logged,xc90)
    logged.put('/api/v1/vehicles/'+xc90['id'],json={'manufacturer':'Volvo','model':'XC90','year':2010,'notes':'Продовжити'})
    with Session(engine()) as db:
        row=db.get(VehicleChecklistItem,provider_id)
        assert row.status=='present' and row.name_uk=='Дзеркало'


def test_rollback_all_parts_and_audit_on_mid_batch_error(logged,xc90,monkeypatch):
    rows=begin(logged,xc90)
    real_stock=dismantling.stock
    calls=[]
    def fail_second(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise RuntimeError('offline simulated failure')
        return real_stock(*args,**kwargs)
    monkeypatch.setattr(dismantling,'stock',fail_second)
    with pytest.raises(RuntimeError):act(logged,xc90,[rows[0]['id'],rows[1]['id']],'receipt')
    assert logged.get('/api/v1/parts').json()['total']==0
    data=logged.get(path(xc90)).json()
    assert data['received_positions']==0
    with engine().connect() as db:
        assert db.execute(text("SELECT count(*) FROM operations WHERE type='receipt'")).scalar_one()==0
        assert db.execute(text('SELECT count(*) FROM categories')).scalar_one()==0


def test_sale_count_is_explicit_not_writeoff_and_receipt_never_replenishes(logged,xc90):
    row=begin(logged,xc90)[0]
    act(logged,xc90,[row['id']],'receipt',quantity=3)
    part=logged.get('/api/v1/parts').json()['items'][0]
    endpoint='/api/v1/parts/'+part['id']+'/operations'
    logged.post(endpoint,json={'type':'write_off','quantity':1,'reason':'Пошкоджена одиниця'})
    assert logged.get(path(xc90)).json()['sold_units']==0
    assert logged.post(endpoint,json={'type':'sale','quantity':2,'reason':'Підтверджений продаж'}).status_code==200
    assert logged.get(path(xc90)).json()['sold_units']==2
    assert logged.get(path(xc90)).json()['stock_positions']==0
    assert act(logged,xc90,[row['id']],'receipt').json()['skipped']==1
    assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==0


def test_migration_preserves_inventory_and_plan_parts(logged,xc90,part):
    before=logged.get('/api/v1/parts/'+part['id']).json()
    run([sys.executable,'-m','alembic','downgrade','b72f03d8e196'],check=True)
    try:
        run([sys.executable,'-m','alembic','upgrade','head'],check=True)
        assert logged.get('/api/v1/parts/'+part['id']).json()==before
        assert logged.get('/api/v1/vehicles/'+xc90['id']).json()['acquisition_date'] is None
        run([sys.executable,'-m','alembic','check'],check=True)
    finally:run([sys.executable,'-m','alembic','upgrade','head'],check=True)


def test_parallel_donors_share_category_tree_without_duplicates(logged,xc90):
    other=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2011}).json()
    first=begin(logged,xc90)[0];second=begin(logged,other)[0]
    def receive(pair):
        vehicle,row=pair
        with Session(engine()) as db:
            result=dismantling.actions(db,vehicle['id'],vehicle['account_id'],DismantlingAction(ids=[row['id']],action='receipt'))
            db.commit();return result['updated']
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(receive,[(xc90,first),(other,second)]))==2
    with engine().connect() as db:
        assert db.execute(text('SELECT count(*) FROM categories')).scalar_one()==3
        assert db.execute(text('SELECT count(*) FROM parts')).scalar_one()==2


def test_relink_previous_receipt_without_duplicate_after_workflow_marker_loss(logged,xc90):
    row=begin(logged,xc90)[0]
    act(logged,xc90,[row['id']],'receipt',quantity=2)
    before=logged.get('/api/v1/parts').json()['items']
    with engine().begin() as db:
        db.execute(text("UPDATE dismantling_items SET part_id=NULL, received_at=NULL, status='unchecked' WHERE id=:id"),{'id':row['id']})
    assert act(logged,xc90,[row['id']],'receipt',quantity=99).json()['updated']==0
    assert logged.get('/api/v1/parts').json()['items']==before
    restored=next(r for r in logged.get(path(xc90)).json()['items'] if r['id']==row['id'])
    assert restored['quantity']==2 and restored['received_at']


def test_category_changes_and_archive_are_preserved(logged,xc90):
    rows=begin(logged,xc90)
    act(logged,xc90,[rows[0]['id']],'receipt')
    first=logged.get('/api/v1/parts').json()['items'][0]
    from app.models import Category
    with Session(engine()) as db:
        category=db.get(Category,first['category_id']);category.name='Моя назва';category.archived=True;db.commit()
    sibling=next(r for r in rows[1:] if r['category_key']==rows[0]['category_key'])
    assert act(logged,xc90,[sibling['id']],'receipt').status_code==409
    with Session(engine()) as db:
        category=db.get(Category,first['category_id']);assert category.name=='Моя назва' and category.archived
    assert logged.get('/api/v1/parts').json()['total']==1


def test_composite_foreign_key_enforces_account_ownership(logged,xc90):
    row=begin(logged,xc90)[0]
    with TestClient(app) as other:account=signup(other,'foreign-constraint@example.test')
    with pytest.raises(IntegrityError):
        with engine().begin() as db:
            db.execute(text('UPDATE dismantling_items SET account_id=:account WHERE id=:id'),{'account':account['id'],'id':row['id']})
