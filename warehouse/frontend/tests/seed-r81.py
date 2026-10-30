"""Create an EMPTY isolated R8.1 browser database. Refuses existing databases."""
import os,sys,json,subprocess
from pathlib import Path
import psycopg
from sqlalchemy.engine import make_url
backend=Path(__file__).resolve().parents[2]/'backend';sys.path.insert(0,str(backend))
url=os.environ['WAREHOUSE_TEST_DATABASE_URL'];u=make_url(url)
if u.host!='127.0.0.1' or u.database!='warehouse_r81_test':raise SystemExit('Dedicated loopback warehouse_r81_test only')
with psycopg.connect('host=127.0.0.1 user=postgres dbname=postgres',autocommit=True) as db:
 if db.execute('select 1 from pg_database where datname=%s',(u.database,)).fetchone():raise SystemExit('Existing fixture retained; refusing reset')
 db.execute('CREATE DATABASE warehouse_r81_test')
os.environ.update(WAREHOUSE_DATABASE_URL=url,WAREHOUSE_COOKIE_SECURE='false',WAREHOUSE_CATALOGUE_WORKER_ENABLED='false')
subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=backend,check=True)
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Account
from app.services.auth import hasher
with Session(engine()) as db:
 owner=Account(email='r81-owner@example.test',name='R8.1 Synthetic Owner',role='DIRECTOR',password_hash=hasher.hash('local-r81-owner-password'));db.add(owner);db.flush()
 worker=Account(email='r81-reader@example.test',name='R8.1 Synthetic Reader',role='MANAGER',workspace_account_id=owner.id,permissions=['catalog.view','inventory.view','catalog.import'],password_hash=hasher.hash('local-r81-reader-password'));db.add(worker);db.commit()
 Path('/tmp/r81-fixture.json').write_text(json.dumps(dict(synthetic=True,database=u.database,owner_id=owner.id)))
print('Created isolated synthetic R8.1 fixture')
