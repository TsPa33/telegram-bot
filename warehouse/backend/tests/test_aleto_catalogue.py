"""Aleto integration on the existing isolated PostgreSQL test runner."""
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.db import engine
from app.main import app
from app.models import Account, Category, Part, Vehicle, Operation, DismantlingItem, Buyer, Order, OrderLine, OrderEvent, OrderReservation
from app.models.aleto import AletoModel, AletoOffer, AletoPrice, AletoApplication, AletoTaxonomy
from app.services.aleto_import import load_package, import_package, money, DICTIONARY
from app.services.inventory import snapshot


@pytest.fixture
def package(tmp_path):
    path = tmp_path / 'aleto.sqlite3'
    with sqlite3.connect(path) as c:
        c.executescript('''
        CREATE TABLE offers(article TEXT PRIMARY KEY,title TEXT,oem TEXT,condition TEXT,price_uah TEXT,price_usd TEXT,url TEXT,checked_at TEXT,price_status TEXT);
        CREATE TABLE applications(model TEXT,article TEXT);
        CREATE TABLE taxonomy_paths(model TEXT,article TEXT,category TEXT,subcategory TEXT,raw_category TEXT,raw_subcategory TEXT);
        ''')
        for i, model in enumerate(('XC40','XC60','XC90')):
            c.execute('INSERT INTO offers VALUES (?,?,?,?,?,?,?,?,?)', (str(i),'Передня панель',None,'Б/В','123.45' if i else '', '3.00', 'https://aleto.ua/ua/detail/panel/', '2026-10-27T19:00:00+00:00','observed' if i else 'missing'))
            c.execute('INSERT INTO applications VALUES (?,?)',('Volvo '+model,str(i)))
            c.execute('INSERT INTO taxonomy_paths VALUES (?,?,?,?,?,?)',('Volvo '+model,str(i),'Кузов','Передняя панель','Кузов','Передняя панель'))
    return path


@pytest.fixture
def data(package):
    return load_package(package)


def owner(db):
    return db.scalar(select(Account).where(Account.role=='DIRECTOR'))


def count(db, cls):
    return db.scalar(select(func.count()).select_from(cls))


def apply(data):
    with Session(engine()) as db:
        result=import_package(db,owner(db).id,data)
        db.commit()
    return result


def test_import_is_additive_idempotent_and_preserves_business_data(logged, vehicle, part, data):
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'receipt','quantity':5,'reason':'Existing stock'}).status_code==200
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'reserve','quantity':1,'reason':'Existing reservation'}).status_code==200
    buyer=logged.post('/api/v1/buyers',json={'name':'Existing buyer','phone':'0501234567'}).json()
    from uuid import uuid4
    order=logged.post('/api/v1/orders',json={'request_key':str(uuid4()),'buyer_id':buyer['id'],
        'lines':[{'part_id':part['id'],'quantity':1,'unit_price':'333.33','currency':'USD'}]})
    assert order.status_code==201,order.text
    protected=(Part,Vehicle,Operation,Category,Buyer,Order,OrderLine,OrderEvent,OrderReservation)
    with Session(engine()) as db:
        aid=owner(db).id
        root=Category(account_id=aid, name='Кузов',kind='category',source='legacy',external_key='body')
        db.add(root);db.flush()
        sub=Category(account_id=aid,name='Передня панель',kind='subcategory',source='legacy',external_key='panel',parent_id=root.id)
        db.add(sub);db.commit()
        original={cls.__tablename__: [snapshot(r) for r in db.scalars(select(cls).order_by(cls.id))] for cls in protected}
    first=apply(data)
    assert first['counts']['offers']['inserted']==3
    assert first['counts']['categories']['inserted']==0
    assert first['counts']['categories']['skipped']==2
    second=apply(data)
    assert all(c['inserted']==c['updated']==0 for c in second['counts'].values())
    with Session(engine()) as db:
        assert count(db,AletoOffer)==3 and count(db,AletoApplication)==3
        for cls in protected:
            assert [snapshot(r) for r in db.scalars(select(cls).order_by(cls.id))]==original[cls.__tablename__]
        assert db.scalar(select(AletoPrice.price_uah).join(AletoOffer,AletoOffer.id==AletoPrice.offer_id).where(AletoOffer.source_article=='0')) is None
        assert all(r.oem is None for r in db.scalars(select(AletoOffer)))


def test_default_cli_dry_run_rolls_back_and_apply_repeats(logged, package, tmp_path):
    with Session(engine()) as db:
        aid=owner(db).id
    report=tmp_path/'report.json'
    command=[sys.executable,'-m','app.services.aleto_import',str(package),'--account-id',aid,'--report',str(report)]
    subprocess.run(command,check=True,capture_output=True,text=True)
    assert json.loads(report.read_text())['committed'] is False
    with Session(engine()) as db:
        assert count(db,AletoOffer)==count(db,Category)==0
    for _ in range(2):
        subprocess.run(command+['--apply'],check=True,capture_output=True,text=True)
    assert json.loads(report.read_text())['counts']['offers']=={'inserted':0,'updated':0,'skipped':3}


def test_price_history_stale_replay_and_conflict_roll_back(logged,data):
    apply(data)
    newer=deepcopy(data)
    for row in newer['offers']:
        row['observed_at']+=timedelta(days=1)
        row['price_uah']=money('200')
    assert apply(newer)['counts']['prices']['inserted']==3
    assert apply(data)['counts']['offers']['skipped']==3
    bad=deepcopy(newer)
    bad['offers'][1]['price_uah']=money('999')
    with pytest.raises(ValueError,match='Conflicting price'):
        apply(bad)
    with Session(engine()) as db:
        assert count(db,AletoPrice)==6
        assert set(db.scalars(select(AletoPrice.price_uah).where(AletoPrice.observed_at==newer['offers'][0]['observed_at'])))=={money('200')}


def test_unknown_subcategory_stays_pending_without_guessing(logged,data):
    for row in data['paths']:
        row['raw_subcategory']=row['subcategory']='Комп'
    result=apply(data)
    assert result['pending_subcategories']=={'Комп':3}
    with Session(engine()) as db:
        assert count(db,Category)==1
        assert all(r.subcategory_id is None and r.normalization_status=='pending' for r in db.scalars(select(AletoTaxonomy)))
    assert DICTIONARY['Рейка рулевая']=='Кермова рейка'
    assert DICTIONARY['Дверь передняя левая Volvo XC40 2019 - 2026']=='Передні ліві двері'
    assert DICTIONARY['Комп'] is None


@pytest.mark.parametrize('price',['NaN','Infinity','-1','1.001','1000000000000'])
def test_invalid_prices_are_rejected(price):
    with pytest.raises(ValueError): money(price)


def test_invalid_source_relationship_rejected_before_writes(package):
    with sqlite3.connect(package) as c:
        c.execute("UPDATE applications SET article='orphan' WHERE article='0'")
    with pytest.raises(ValueError):load_package(package)


def test_ambiguous_existing_category_rejects_entire_import(logged,data):
    with Session(engine()) as db:
        aid=owner(db).id
        for key in ('one','two'):
            db.add(Category(account_id=aid,name='Кузов',kind='category',source='legacy',external_key=key))
        db.commit()
    with pytest.raises(ValueError,match='Ambiguous'):
        apply(data)
    with Session(engine()) as db:
        assert count(db,AletoOffer)==0 and count(db,AletoModel)==0 and count(db,Category)==2


def test_catalogue_filtering_tenant_isolation_and_no_false_year_fitment(logged, data):
    apply(data)
    v=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC40','year':1999}).json()
    url=f"/api/v1/vehicles/{v['id']}/aleto-catalog"
    response=logged.get(url)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['total']==1 and result['year_compatibility']=='unverified'
    assert result['items'][0]['price_uah'] is None
    node=result['categories'][0]
    assert logged.get(url,params={'subcategory_id':node['subcategory_id']}).json()['total']==1
    assert logged.get(url,params={'category_id':'not-owned'}).json()['total']==0
    assert logged.get(url,params={'q':'missing'}).json()['total']==0
    with TestClient(app) as other:
        r=other.post('/api/v1/auth/register',json={'email':'other@example.test','name':'Other','password':'other-long-password'})
        other.headers['X-CSRF-Token']=r.json()['csrf_token']
        assert other.get(url).status_code==404
        ov=other.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC40','year':2020}).json()
        assert other.get(f"/api/v1/vehicles/{ov['id']}/aleto-catalog").json()['total']==0
    assert logged.get(url,params={'limit':201}).status_code==422
    assert logged.get(url,params={'offset':-1}).status_code==422


def test_vehicle_workflow_adds_excluded_types_only_and_explicit_receipt_uses_merged_categories(logged,data):
    apply(data)
    catalog=logged.get('/api/v1/vehicle-catalog').json()
    assert {'XC40','XC60','XC90'}<=set(next(b['models'] for b in catalog['brands'] if b['name']=='Volvo'))
    v=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC60','year':2020}).json()
    base=f"/api/v1/vehicles/{v['id']}/dismantling"
    assert logged.post(base+'/prepare').status_code==200
    assert logged.post(base+'/prepare').json()['created']==0
    with Session(engine()) as db:
        ref=db.scalar(select(DismantlingItem).where(DismantlingItem.vehicle_id==v['id'],DismantlingItem.source=='aleto.v1'))
        assert ref is not None and not ref.included
        assert count(db,Part)==0
        rid=ref.id
        roots=set(db.scalars(select(Category.id)))
    assert logged.post(base+'/plan',json={'ids':[rid],'included':True}).status_code==200
    assert logged.post(base+'/actions',json={'ids':[rid],'action':'dismantled'}).status_code==200
    receipt=logged.post(base+'/actions',json={'ids':[rid],'action':'receipt'})
    assert receipt.status_code==200,receipt.text
    with Session(engine()) as db:
        p=db.scalar(select(Part))
        assert p.category_id in roots and p.subcategory_id in roots
        assert p.quantity==1 and p.selling_price is None and p.unit_cost is None
    other=logged.post('/api/v1/vehicles',json={'manufacturer':'Toyota','model':'RAV4','year':2020}).json()
    logged.post(f"/api/v1/vehicles/{other['id']}/dismantling/prepare")
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(DismantlingItem).where(DismantlingItem.vehicle_id==other['id'],DismantlingItem.source=='aleto.v1'))==0


def test_cli_rejects_non_test_database_before_connecting(package,tmp_path):
    env={**os.environ,'WAREHOUSE_DATABASE_URL':'postgresql+psycopg://postgres@127.0.0.1/warehouse_production'}
    result=subprocess.run([sys.executable,'-m','app.services.aleto_import',str(package),'--account-id','unused','--apply'],env=env,capture_output=True,text=True)
    assert result.returncode!=0 and 'Only a dedicated' in result.stderr


def test_concurrent_imports_serialize_without_duplicates(logged,data):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:apply(data),range(2)))
    assert sorted(r['counts']['offers']['inserted'] for r in results)==[0,3]
    with Session(engine()) as db:
        assert count(db,AletoOffer)==3 and count(db,AletoPrice)==3 and count(db,Category)==2


def test_reference_read_permission_and_no_http_import_surface(logged,data,monkeypatch):
    apply(data)
    v=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2020}).json()
    from app.services.auth import hasher
    with Session(engine()) as db:
        user=Account(email='limited@example.test',name='Limited',password_hash=hasher.hash('limited-long-password'),
                     role='MANAGER',workspace_account_id=owner(db).id,permissions=['vehicles.view'])
        db.add(user);db.commit()
        mid=user.id
    with TestClient(app) as c:
        r=c.post('/api/v1/auth/login',json={'email':'limited@example.test','password':'limited-long-password'})
        assert r.status_code==200,r.text
        c.headers['X-CSRF-Token']=r.json()['csrf_token']
        url=f"/api/v1/vehicles/{v['id']}/aleto-catalog"
        assert c.get(url).status_code==403
        with Session(engine()) as db:
            db.get(Account,mid).permissions=['vehicles.view','catalog.view']
            db.commit()
        assert c.get(url).status_code==200
        assert c.post(url,json={}).status_code==405
    with Session(engine()) as db:
        with pytest.raises(ValueError,match='DIRECTOR'):
            import_package(db,mid,data)


def test_aleto_migration_roundtrip_keeps_existing_stock_and_history(logged,vehicle,part):
    with Session(engine()) as db:
        before={cls.__tablename__:[snapshot(r) for r in db.scalars(select(cls).order_by(cls.id))] for cls in (Part,Vehicle,Operation)}
    try:
        subprocess.run([sys.executable,'-m','alembic','downgrade','b94f62d18e07'],check=True,capture_output=True)
        for _ in range(2):
            subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)
        subprocess.run([sys.executable,'-m','alembic','check'],check=True,capture_output=True)
        with Session(engine()) as db:
            for cls in (Part,Vehicle,Operation):
                assert [snapshot(r) for r in db.scalars(select(cls).order_by(cls.id))]==before[cls.__tablename__]
    finally:
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)


@pytest.mark.parametrize('environment,name,flag,railway,allowed',[
    ('', 'warehouse_aleto_test', False, None, True),
    ('staging', 'warehouse_staging', True, 'warehouse-staging', True),
    ('staging', 'carpot_warehouse_staging', True, None, True),
    ('staging', 'warehouse_staging', False, 'warehouse-staging', False),
    ('', 'warehouse_staging', True, None, False),
    ('production', 'warehouse_aleto_test', False, None, False),
    ('production', 'warehouse_staging', True, 'warehouse-staging', False),
    ('staging', 'warehouse_production', True, 'warehouse-staging', False),
    ('staging', 'warehouse_staging', True, 'production', False),
])
def test_staging_target_requires_explicit_matching_environment(environment,name,flag,railway,allowed):
    from app.services.aleto_import import validate_target
    url='postgresql+psycopg://user@localhost/'+name
    if allowed:
        validate_target(url,environment,flag,railway)
    else:
        with pytest.raises(ValueError):validate_target(url,environment,flag,railway)


def test_bundled_package_is_portable_and_matches_full_catalogue():
    from app.services.aleto_import import BUNDLED_PACKAGE
    dataset=load_package(BUNDLED_PACKAGE)
    assert dataset['sha256']=='c2cdde72685a6f41c70922e569fd8eae81e8bcbd292273fa411314dd920dccd3'
    assert (len(dataset['offers']),len(dataset['applications']),len(dataset['paths']))==(7246,10112,14400)
    assert {model for model,_ in dataset['applications']}=={'Volvo XC40','Volvo XC60','Volvo XC90'}


def test_gzip_package_corruption_is_rejected(tmp_path):
    bad=tmp_path/'corrupt.sqlite3.gz'
    bad.write_bytes(b'not a gzip archive')
    with pytest.raises(OSError):load_package(bad)
