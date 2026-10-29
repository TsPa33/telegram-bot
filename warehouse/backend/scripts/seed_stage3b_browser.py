"""Create fresh donors in the existing disposable synthetic reference DB; no cleanup."""
import os,sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-disposable',action='store_true',required=True);args=p.parse_args()
u=make_url(os.environ['WAREHOUSE_TEST_DATABASE_URL'])
if u.host not in ('localhost','127.0.0.1') or u.database!='warehouse_stage3b_browser_test':raise SystemExit('Dedicated local browser database required')
os.environ['WAREHOUSE_DATABASE_URL']=str(os.environ['WAREHOUSE_TEST_DATABASE_URL']);os.environ['WAREHOUSE_COOKIE_SECURE']='false';os.environ['WAREHOUSE_CATALOGUE_WORKER_ENABLED']='false'
from fastapi.testclient import TestClient
from app.main import app
from uuid import uuid4
file=Path('/tmp/stage3b-browser-fixture.json');fixture=json.loads(file.read_text());fixture['vehicles']=[]
with TestClient(app) as c:
 r=c.post('/api/v1/auth/login',json={'email':'stage2c-owner@example.test','password':'local-stage2c-password'});assert r.status_code==200
 c.headers['X-CSRF-Token']=r.json()['csrf_token']
 for width in (1440,390):
  r=c.post('/api/v1/vehicles',json=dict(manufacturer='Volvo',model='XC60',year=2018,donor_id='LOCAL-3B-'+str(uuid4()),acquisition_date='2026-01-01',acquisition_cost='0'));assert r.status_code==201,r.text
  fixture['vehicles'].append(dict(width=width,id=r.json()['id']))
file.write_text(json.dumps(fixture,indent=2)+'\n');print('Created two new local donors; existing donors and catalogue unchanged')
