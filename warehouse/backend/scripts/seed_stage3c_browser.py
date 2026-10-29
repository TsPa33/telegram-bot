"""Seed a dedicated synthetic Stage 3C database and fresh donors. Never clears data."""
import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
url=os.environ['WAREHOUSE_TEST_DATABASE_URL'];u=make_url(url)
if u.host not in ('localhost','127.0.0.1') or u.database not in ('warehouse_stage3c_browser_test','warehouse_stage3c_browser2_test'):raise SystemExit('Dedicated disposable loopback DB required')
os.environ.update(WAREHOUSE_DATABASE_URL=url,WAREHOUSE_COOKIE_SECURE='false',WAREHOUSE_CATALOGUE_WORKER_ENABLED='false')
from sqlalchemy import select,func,insert
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.db import engine
from app.main import app
from app.models import Account,Part,Vehicle
from app.models.catalogue import CatalogueEntity,CatalogueOffer,CataloguePrice,CataloguePath,CatalogueApplication,CatalogueSource
from app.models.canonical import CanonicalType,CanonicalPlacement,CanonicalVariant,CanonicalMapping,CanonicalState,CanonicalRun
from app.services.canonical_catalogue import analyze
from app.services.catalogue_format import digest
from uuid import uuid4
with Session(engine()) as db:
 seeded=db.scalar(select(func.count()).select_from(CatalogueOffer))
 if seeded and db.scalar(select(func.count()).select_from(CatalogueSource).where(CatalogueSource.name!='synthetic-stage3c')):raise SystemExit('Foreign fixture; refusing changes')
 exists=db.scalar(select(func.count()).select_from(Account))
with TestClient(app) as c:
 r=c.post('/api/v1/auth/login' if exists else '/api/v1/auth/register',json={**({} if exists else {'name':'Synthetic 3C Owner'}),'email':'stage3c-owner@example.test','password':'local-stage3c-password'});assert r.status_code in (200,201),r.text
 c.headers['X-CSRF-Token']=r.json()['csrf_token'];owner=r.json()['user']['id']
 if not seeded:
  with Session(engine()) as db:
   brand=CatalogueEntity(id=str(uuid4()),kind='manufacturer',name='Volvo',normalized_name='volvo',identity_key=digest(['3c','brand']));db.add(brand);db.flush()
   model=CatalogueEntity(id=str(uuid4()),kind='model',name='XC40',normalized_name='xc40',parent_id=brand.id,parent_kind='manufacturer',identity_key=digest(['3c','model']));src=CatalogueSource(id=str(uuid4()),name='synthetic-stage3c');db.add_all([model,src]);db.flush()
   for i,(name,oem,category,sub,side,position) in enumerate([('Фара передня ліва Volvo XC40','OEM-123-A','Оптика','Фари','ліва','передня')]*3+[('Бампер передній Volvo XC40','OEM-B','Кузов','Бампери','','передня'),('Зовнішнє дзеркало ліве Volvo XC40','OEM-C','Кузов','Дзеркала','ліва','')]):
    from datetime import datetime,timezone
    date=datetime(2026,10,27,12,tzinfo=timezone.utc);link='https://example.test/synthetic-3c-'+str(i)
    offer=CatalogueOffer(id=str(uuid4()),source_id=src.id,source_article='SYNTHETIC-3C-'+str(i),properties=dict(part_name=name,oem=oem,condition='used',side=side,position=position,source_url=link),observed_at=date);db.add(offer);db.flush()
    db.add(CatalogueApplication(offer_id=offer.id,model_id=model.id));db.add(CataloguePrice(id=str(uuid4()),offer_id=offer.id,observed_at=date,price_uah=100+i*50,source_url=link));db.add(CataloguePath(id=str(uuid4()),offer_id=offer.id,model_id=model.id,path_key=digest(['3c',i]),raw=dict(category=category,subcategory=sub,part_name=name,side=side,position=position)))
   db.flush();plan=analyze(db)
   for cls,key in [(CanonicalType,'types'),(CanonicalPlacement,'placements'),(CanonicalVariant,'variants'),(CanonicalMapping,'mappings')]:
    if plan[key]:db.execute(insert(cls),plan[key])
   state=db.get(CanonicalState,1);state.snapshot_sha=plan['snapshot_sha'];state.policy=plan['policy'];assert db.scalar(select(func.count()).select_from(CanonicalRun))==0;db.commit()
 vehicles=[]
 for width in (1440,390):
  r=c.post('/api/v1/vehicles',json=dict(manufacturer='Volvo',model='XC40',year=2020,donor_id='SYNTHETIC-3C-'+str(uuid4()),acquisition_date='2026-01-01',acquisition_cost='0'));assert r.status_code==201,r.text
  v=r.json();base='/api/v1/vehicles/'+v['id']
  # The production configuration workflow is exercised by the browser separately;
  # this fixture has explicit verified headlamp equipment evidence.
  facts=[dict(field=k,value=value,kind='manual',reference='Synthetic local equipment proof',confidence='verified') for k,value in dict(manufacturer='Volvo',model='XC40',year=2020,options=['standard-headlamps'],body_type='SUV',drive='AWD',transmission='automatic').items()]
  proof=c.post(base+'/configuration/preview',json={'facts':facts}).json()
  r=c.post(base+'/configuration/confirm',json=dict(preview_id=proof['id'],token=proof['token'],confirm=True));assert r.status_code==200,r.text
  path=base+'/virtual-dismantling';state=c.get(path).json();r=c.post(path+'/activate',json=dict(facts=[],etag=state['etag'],request_key=str(uuid4()),confirm=True));assert r.status_code==200,r.text
  state=c.get(path).json();target=next(i for i in state['items'] if i['name']=='Фара' and i['position']=='передня ліва')
  with Session(engine()) as db:
   part=db.get(Part,target['part_id']);part.oem_number='OEM-123-A';part.condition='used'
   bumper=next((i for i in state['items'] if i['name']=='Бампер' and i['position']=='передня'),None)
   if bumper:p=db.get(Part,bumper['part_id']);p.oem_number='OEM-B';p.condition='used'
   db.commit()
  vehicles.append(dict(width=width,id=v['id'],target=target,bumper=bumper,total=state['total']))
Path('/tmp/stage3c-browser-fixture.json').write_text(json.dumps(dict(synthetic=True,owner_id=owner,vehicles=vehicles),ensure_ascii=False,indent=2)+'\n')
print('Created two fresh synthetic donors; previous donors unchanged; dedicated local test DB only')
