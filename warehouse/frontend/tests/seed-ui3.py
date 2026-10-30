"""Fresh, disposable synthetic UI-3 fixture. Never modifies its source DB."""
import os,sys,json,subprocess
from pathlib import Path
from uuid import uuid4
backend=Path(__file__).resolve().parents[2]/'backend';sys.path.insert(0,str(backend))
from sqlalchemy.engine import make_url
url=os.environ['WAREHOUSE_TEST_DATABASE_URL'];u=make_url(url)
if u.host!='127.0.0.1' or u.database!='warehouse_ui3_test':raise SystemExit('Dedicated loopback warehouse_ui3_test only')
import psycopg
with psycopg.connect('host=127.0.0.1 user=postgres dbname=postgres',autocommit=True) as maintenance:
 if maintenance.execute('select 1 from pg_database where datname=%s',(u.database,)).fetchone():raise SystemExit('Existing database retained; refusing reseed')
 maintenance.execute('CREATE DATABASE warehouse_ui3_test')
os.environ.update(WAREHOUSE_DATABASE_URL=url,WAREHOUSE_COOKIE_SECURE='false',WAREHOUSE_CATALOGUE_WORKER_ENABLED='false')
subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=backend,check=True)
from sqlalchemy import create_engine,select,insert,update
from sqlalchemy.orm import Session
from app.db import engine,Base
from app.models import Account,Part,Vehicle,Category
from app.models.catalogue import CatalogueOffer,CatalogueSource,CatalogueState
from app.models.canonical import CanonicalState
from app.services.auth import hasher
source=create_engine('postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage3c_browser2_test')
with source.connect() as read,engine().begin() as target:
 read.exec_driver_sql('SET TRANSACTION READ ONLY')
 assert set(read.execute(select(CatalogueSource.name)).scalars())=={'synthetic-stage3c'}
 assert all(a.startswith('SYNTHETIC-3C-') for a in read.execute(select(CatalogueOffer.source_article)).scalars())
 state=dict(read.execute(select(CanonicalState.__table__)).mappings().one());assert not state['policy'].get('alias_ids')
 names=['catalogue_sources','catalogue_entities','catalogue_offers','catalogue_applications','catalogue_prices','catalogue_paths','canonical_types','canonical_placements','canonical_variants','canonical_mappings']
 for name in names:
  table=Base.metadata.tables[name];rows=[dict(r) for r in read.execute(select(table)).mappings()]
  if name=='catalogue_entities':rows.sort(key=lambda r:0 if r['kind']=='manufacturer' else 1)
  for row in rows:target.execute(insert(table),row)
 for cls in (CatalogueState,CanonicalState):
  row=dict(read.execute(select(cls.__table__)).mappings().one());rid=row.pop('id');target.execute(update(cls).where(cls.id==rid).values(**row))
 read.rollback()
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
 r=c.post('/api/v1/auth/register',json=dict(name='UI3 Synthetic Owner',email='ui3-owner@example.test',password='local-ui3-owner-password'));assert r.status_code==201,r.text
 owner=r.json()['user']['id'];c.headers['X-CSRF-Token']=r.json()['csrf_token']
 vehicles=[]
 for n in range(2):
  r=c.post('/api/v1/vehicles',json=dict(manufacturer='Volvo',model='XC40' if n==0 else 'XC90',year=2020 if n==0 else 2018,donor_id='UI3-SYNTHETIC-'+str(uuid4()),acquisition_date='2026-01-01',acquisition_cost='0'));assert r.status_code==201,r.text;vehicles.append(r.json())
 v=vehicles[0];base='/api/v1/vehicles/'+v['id'];facts=[dict(field=k,value=value,kind='manual',reference='Synthetic fixture equipment proof',confidence='verified') for k,value in dict(manufacturer='Volvo',model='XC40',year=2020,options=['standard-headlamps'],body_type='SUV',drive='AWD',transmission='automatic').items()]
 proof=c.post(base+'/configuration/preview',json={'facts':facts}).json();r=c.post(base+'/configuration/confirm',json=dict(preview_id=proof['id'],token=proof['token'],confirm=True));assert r.status_code==200,r.text
 state=c.get(base+'/virtual-dismantling').json();r=c.post(base+'/virtual-dismantling/activate',json=dict(facts=[],etag=state['etag'],request_key=str(uuid4()),confirm=True));assert r.status_code==200,r.text
 state=c.get(base+'/virtual-dismantling').json();headlamp=next(i for i in state['items'] if i['name']=='Фара' and i['position']=='передня ліва');bumper=next(i for i in state['items'] if i['name']=='Бампер' and i['position']=='передня')
 with Session(engine()) as db:
  p=db.get(Part,headlamp['part_id']);p.oem_number='OEM-123-A';p.condition='used';p.selling_price=140
  p=db.get(Part,bumper['part_id']);p.oem_number='OEM-B';p.condition='used'
  cat=Category(account_id=owner,name='Синтетичні деталі',source='ui3-synthetic',kind='category',external_key='ui3-root');db.add(cat);db.flush()
  sub=Category(account_id=owner,name='Довгі назви',source='ui3-synthetic',kind='subcategory',external_key='ui3-sub',parent_id=cat.id);other=Category(account_id=owner,name='Додаткові',source='ui3-synthetic',kind='subcategory',external_key='ui3-sub-2',parent_id=cat.id);db.add_all([sub,other]);db.flush()
  extras=[]
  for n in range(125):
   part=Part(account_id=owner,vehicle_id=v['id'],name='UI3 Синтетична деталь '+str(n)+(' із довгою назвою та уточненням установчої позиції без підтвердженої взаємозамінності — для локального UI тесту' if n==124 else ''),category_id=cat.id,subcategory_id=sub.id if n<120 else other.id,article_number='UI3-ARTICLE-'+str(n),oem_number='SYNTH-UI3-'+str(n),condition='used',quantity=0 if n==2 else 3,reserved_quantity=1 if n==0 else 0,selling_price=25 if n==0 else 0 if n==1 else None,currency='USD' if n==0 else 'UAH',assortment_enabled=n!=3,archived=n==4,location='UI3 fixture shelf')
   db.add(part);db.flush();extras.append(dict(id=part.id,name=part.name))
  second=Part(account_id=owner,vehicle_id=vehicles[1]['id'],name='UI3 Інший автомобіль',quantity=1,condition='unknown');db.add(second)
  worker=Account(email='ui3-reader@example.test',name='UI3 Read Only',password_hash=hasher.hash('local-ui3-reader-password'),role='MANAGER',workspace_account_id=owner,permissions=['inventory.view','vehicles.view','catalog.view','audit.view']);db.add(worker);db.commit()
  cat_id=cat.id;sub_id=sub.id;other_id=other.id
with TestClient(app) as c:
 r=c.post('/api/v1/auth/register',json=dict(name='UI3 Other Workspace',email='ui3-other@example.test',password='local-ui3-other-password'));assert r.status_code==201,r.text
 foreign=r.json()['user']['id']
 with Session(engine()) as db:
  p=Part(account_id=foreign,name='UI3 FOREIGN forbidden',quantity=1,condition='used');db.add(p);db.commit();foreign_id=p.id
fixture=dict(synthetic=True,owner_id=owner,vehicles=vehicles,target=headlamp['part_id'],bumper=bumper['part_id'],extras=extras,category_id=cat_id,subcategory_id=sub_id,other_subcategory_id=other_id,foreign_id=foreign_id,virtual_positions=state['total'])
Path('/tmp/ui3-fixture.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n');print('Created fresh UI-3 synthetic DB; source reference read-only; no real Volvo data')
