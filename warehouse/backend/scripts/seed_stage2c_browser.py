"""Destructive fixture seed ONLY for an explicit disposable loopback Warehouse test DB."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--confirm-disposable',action='store_true',required=True)
p.add_argument('--output',type=Path,default=Path('/tmp/stage2c-browser-fixture.json'))
args=p.parse_args()
import os
from sqlalchemy.engine import make_url
url=os.environ.get('WAREHOUSE_TEST_DATABASE_URL','');u=make_url(url)
if u.host not in ('127.0.0.1','localhost') or not (u.database or '').startswith('warehouse') or not u.database.endswith('_test'):raise SystemExit('Explicit loopback warehouse*_test required')
os.environ['WAREHOUSE_DATABASE_URL']=url
import os,json
os.environ['WAREHOUSE_CATALOGUE_WORKER_ENABLED']='false';os.environ['WAREHOUSE_COOKIE_SECURE']='false'
from sqlalchemy import text,select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.db import engine
from app.main import app
from app.models import DismantlingItem,Part,now
from app.services.dismantling import receipt
from types import SimpleNamespace
from uuid import uuid4
from pathlib import Path
with engine().begin() as c:
 c.execute(text('TRUNCATE accounts,catalogue_sources,catalogue_entities,catalogue_state,canonical_types,canonical_runs,canonical_state CASCADE'))
 c.execute(text('INSERT INTO catalogue_state(id,revision) VALUES(1,0)'));c.execute(text("INSERT INTO canonical_state(id,snapshot_sha,policy) VALUES(1,NULL,'{}'::json)"))
with TestClient(app) as c:
 u=c.post('/api/v1/auth/register',json=dict(name='Stage2C Local Owner',email='stage2c-owner@example.test',password='local-stage2c-password')).json();c.headers['X-CSRF-Token']=u['csrf_token']
 vehicles=[]
 for width in [1440,390]:
  r=c.post('/api/v1/vehicles',json=dict(manufacturer='Volvo',model='XC60',year=2018,donor_id='STAGE2C-LOCAL-'+str(width),acquisition_date='2026-01-01',acquisition_cost='0'));assert r.status_code==201,r.text
  v=r.json();vehicles.append(dict(width=width,id=v['id']))
  assert c.post('/api/v1/vehicles/'+v['id']+'/dismantling/start').status_code==200
  with Session(engine()) as db:
   rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==v['id']).order_by(DismantlingItem.id)));db.info['actor_id']=u['user']['id']
   for row in rows[:30]:
    row.status='dismantled';receipt(db,row,SimpleNamespace(quantity=1,condition='used',location='Local synthetic fixture',selling_price=None),row.account_id)
    db.get(Part,row.part_id).selling_price=137
   rows[32].included=False;sold_part=rows[29].part_id;db.commit()
  assert c.post('/api/v1/parts/'+sold_part+'/operations',json=dict(type='sale',quantity=1,sale_price='50.00',sale_currency='UAH',request_key=str(uuid4()))).status_code==200
 args.output.write_text(json.dumps(dict(owner_id=u['user']['id'],vehicles=vehicles)))
 print('Seeded two local XC60 fixtures: 33 legacy positions, 29 positive stocks, 30 receipt histories each')

# One clearly synthetic unresolved source for exercising the owner review UI.
from app.models.catalogue import CatalogueEntity,CatalogueSource,CatalogueOffer,CatalogueApplication,CataloguePath
from app.services.catalogue_format import digest
from app.services.canonical_rules import sid
with Session(engine()) as db:
    brand=sid('stage2c-browser-brand');model=sid('stage2c-browser-model');provider=sid('stage2c-browser-source');offer=sid('stage2c-browser-offer')
    db.add(CatalogueEntity(id=brand,kind='manufacturer',name='Volvo',normalized_name='volvo',identity_key=digest(['stage2c','brand'])));db.flush()
    db.add(CatalogueEntity(id=model,kind='model',name='XC60',normalized_name='xc60',parent_id=brand,parent_kind='manufacturer',identity_key=digest(['stage2c','model'])));db.add(CatalogueSource(id=provider,name='synthetic-stage2c-browser'));db.flush()
    db.add(CatalogueOffer(id=offer,source_id=provider,source_article='SYNTHETIC-OWNER-REVIEW',properties={'part_name':'Насос сервісний тестовий','oem':None,'source_url':'https://example.test/synthetic-fixture','condition':'synthetic test only'},observed_at=now()));db.flush()
    db.add(CatalogueApplication(offer_id=offer,model_id=model));db.flush()
    db.add(CataloguePath(id=sid('stage2c-browser-path'),offer_id=offer,model_id=model,path_key=digest(['synthetic']),raw={'category':'Силовий агрегат','subcategory':'Насоси'}));db.commit()
