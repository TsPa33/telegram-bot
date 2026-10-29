"""Disposable local bulk/receipt fixtures. Never modifies staging or invokes publication."""
import os,sys,argparse,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-disposable',action='store_true',required=True);p.add_argument('--output',type=Path,default=Path('/tmp/stage2e-browser-fixture.json'));args=p.parse_args()
url=os.environ.get('WAREHOUSE_TEST_DATABASE_URL','');u=make_url(url)
if u.host not in ('127.0.0.1','localhost') or not (u.database or '').startswith('warehouse') or not u.database.endswith('_test'):raise SystemExit('Explicit loopback warehouse*_test required')
os.environ['WAREHOUSE_DATABASE_URL']=url;os.environ['WAREHOUSE_COOKIE_SECURE']='false';os.environ['WAREHOUSE_CATALOGUE_WORKER_ENABLED']='false'
subprocess.run([sys.executable,str(Path(__file__).with_name('seed_stage2d_browser.py')),'--confirm-disposable','--output',str(args.output)],check=True)
from fastapi.testclient import TestClient
from sqlalchemy import insert
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import Vehicle,DismantlingItem
from app.models.canonical import CanonicalState
from app.models.catalogue import CatalogueState
from app.services.canonical_rules import sid
from app.services.vehicle_configuration import basis
fixture=json.loads(args.output.read_text());fixture['counters']=[]
with TestClient(app) as c:
 r=c.post('/api/v1/auth/login',json=dict(email='stage2c-owner@example.test',password='local-stage2c-password'));assert r.status_code==200;c.headers['X-CSRF-Token']=r.json()['csrf_token']
 for width in [1440,390]:
  r=c.post('/api/v1/vehicles',json=dict(manufacturer='Volvo',model='XC60',year=2018,donor_id='STAGE2E-COUNTER-'+str(width),acquisition_date='2026-01-01',acquisition_cost='0'));assert r.status_code==201
  fixture['counters'].append(dict(width=width,id=r.json()['id']))
with Session(engine()) as db:
 for group,n in [('vehicles',1105),('counters',196)]:
  for data in fixture[group]:
   v=db.get(Vehicle,data['id']);rows=[]
   for i in range(n):
    cat='Масовий тест' if group=='vehicles' else 'Основні' if i<194 else 'Резерв';sub=('Підкатегорія A' if i<700 else 'Підкатегорія Б') if group=='vehicles' else 'Контроль'
    rows.append(dict(id=sid('stage2e-row',v.id,i),account_id=v.account_id,vehicle_id=v.id,source='synthetic.stage2e',catalog_key=str(i),category_key=sid(cat),category_name=cat,subcategory_key=sid(sub),subcategory_name=sub,name=('Тестова деталь ' if group=='vehicles' else 'Контрольна деталь ')+f'{i:04d}',position='',status='unchecked',quantity=1,included=True,plan_v3={'placement_id':sid('stage2e-placement',i),'canonical_part_type_id':sid('stage2e-type',i),'inspection':'unchecked','snapshot':{'applicability_status':'confirmed','reference_prices':[{'median':'9999.00','label':'Synthetic reference only'}]}}))
   for start in range(0,len(rows),200):db.execute(insert(DismantlingItem).values(rows[start:start+200]))
   v.dismantling_v3={'revision':1,'version':'synthetic.stage2e.fixture','vehicle_basis':basis(v),'catalogue_snapshot':db.get(CanonicalState,1).snapshot_sha,'catalogue_revision':db.get(CatalogueState,1).revision,'pending_review':[]}
 db.commit()
fixture.update(synthetic=True,reference_fixture=True,real_B_tested=False)
args.output.write_text(json.dumps(fixture,indent=2)+'\n');print('Stage2E: two 1105-row plans + two 196-row counter fixtures, unchecked; no stock for these plans')
