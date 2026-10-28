"""Disposable local Quick Create fixtures; NEVER run against staging.

Build reference rows as fixtures, without calling canonical publish or queue APIs.
"""
import os,sys,argparse,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-disposable',action='store_true',required=True);p.add_argument('--output',type=Path,default=Path('/tmp/stage2d-browser-fixture.json'));args=p.parse_args()
url=os.environ.get('WAREHOUSE_TEST_DATABASE_URL','');u=make_url(url)
if u.host not in ('127.0.0.1','localhost') or not (u.database or '').startswith('warehouse') or not u.database.endswith('_test'):raise SystemExit('Explicit loopback warehouse*_test required')
os.environ['WAREHOUSE_DATABASE_URL']=url;os.environ['WAREHOUSE_COOKIE_SECURE']='false';os.environ['WAREHOUSE_CATALOGUE_WORKER_ENABLED']='false'
subprocess.run([sys.executable,str(Path(__file__).with_name('seed_stage2c_browser.py')),'--confirm-disposable','--output',str(args.output)],check=True)
from fastapi.testclient import TestClient
from sqlalchemy import select,insert,func
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import now
from app.models.catalogue import CatalogueOffer,CatalogueApplication,CataloguePath,CatalogueSource,CatalogueEntity
from app.models.canonical import CanonicalType,CanonicalPlacement,CanonicalVariant,CanonicalMapping,CanonicalState,CanonicalRun
from app.services.canonical_catalogue import analyze
from app.services.canonical_rules import sid
from app.services.catalogue_format import digest
fixture=json.loads(args.output.read_text());fixture['historical']=fixture.pop('vehicles');fixture['vehicles']=[]
with TestClient(app) as c:
 r=c.post('/api/v1/auth/login',json=dict(email='stage2c-owner@example.test',password='local-stage2c-password'));assert r.status_code==200
 c.headers['X-CSRF-Token']=r.json()['csrf_token']
 for width in [1440,390]:
  r=c.post('/api/v1/vehicles',json=dict(manufacturer='Volvo',model='XC60',year=2018,donor_id='STAGE2D-NEW-'+str(width),acquisition_date='2026-01-01',acquisition_cost='0'));assert r.status_code==201,r.text
  fixture['vehicles'].append(dict(width=width,id=r.json()['id']))
with Session(engine()) as db:
 model=db.scalar(select(CatalogueEntity).where(CatalogueEntity.kind=='model'));src=db.scalar(select(CatalogueSource));offer=sid('stage2d-browser-mirror')
 db.add(CatalogueOffer(id=offer,source_id=src.id,source_article='SYNTHETIC-REFINED-MIRROR',properties={'part_name':'Зовнішнє дзеркало переднє ліве Volvo XC60','oem':None,'source_url':'https://example.test/synthetic-mirror','condition':'synthetic test only'},observed_at=now()));db.flush()
 db.add(CatalogueApplication(offer_id=offer,model_id=model.id));db.flush()
 db.add(CataloguePath(id=sid('stage2d-browser-mirror-path'),offer_id=offer,model_id=model.id,path_key=digest(['stage2d-mirror']),raw={'category':'Кузов','subcategory':'Дзеркала'}));db.flush()
 plan=analyze(db)  # Pure fixture construction, no publication command.
 for cls,rows in [(CanonicalType,plan['types']),(CanonicalPlacement,plan['placements']),(CanonicalVariant,plan['variants']),(CanonicalMapping,plan['mappings'])]:
  for start in range(0,len(rows),300):db.execute(insert(cls).values(rows[start:start+300]))
 state=db.get(CanonicalState,1);state.snapshot_sha=plan['snapshot_sha'];state.policy=plan['policy'];db.commit()
 assert db.scalar(select(func.count()).select_from(CanonicalRun))==0
fixture.update(synthetic=True,real_B_tested=False,reference_fixture=True)
args.output.write_text(json.dumps(fixture,indent=2)+'\n');print('Stage2D reference fixture ready; no canonical publish or jobs invoked')
