"""Create a fresh, synthetic-only UI-5 DB. Refuses existing DBs; never resets/reseeds."""
import os,sys,json,subprocess
from pathlib import Path
from datetime import datetime,timedelta,timezone
from decimal import Decimal
backend=Path(__file__).resolve().parents[2]/'backend';sys.path.insert(0,str(backend))
from sqlalchemy.engine import make_url
url=os.environ['WAREHOUSE_TEST_DATABASE_URL'];u=make_url(url)
if u.host!='127.0.0.1' or u.database!='warehouse_ui5_test':raise SystemExit('Dedicated loopback warehouse_ui5_test only')
import psycopg
with psycopg.connect('host=127.0.0.1 user=postgres dbname=postgres',autocommit=True) as c:
 if c.execute('select 1 from pg_database where datname=%s',(u.database,)).fetchone():raise SystemExit('Existing database retained; refusing reseed')
 c.execute('CREATE DATABASE warehouse_ui5_test')
os.environ.update(WAREHOUSE_DATABASE_URL=url,WAREHOUSE_COOKIE_SECURE='false',WAREHOUSE_CATALOGUE_WORKER_ENABLED='false')
subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=backend,check=True)
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from app.models import Account,Part,Vehicle,Operation
from app.models.orders import Buyer,Order,OrderLine,OrderEvent
from app.services.auth import hasher
from sqlalchemy.orm import Session
with TestClient(app) as c:
 r=c.post('/api/v1/auth/register',json=dict(name='UI5 Synthetic Owner',email='ui5-owner@example.test',password='local-ui5-owner-password'));assert r.status_code==201,r.text
 owner=r.json()['user']['id']
with Session(engine()) as db:
 vehicles=[]
 for n in range(2):
  v=Vehicle(account_id=owner,manufacturer='Volvo',model='XC90' if n==0 else 'XC60',year=2018 if n==0 else 2020,number=n+1,donor_id='UI5-SYNTHETIC-'+str(n),acquisition_date='2026-01-01',acquisition_cost=0);db.add(v);db.flush();vehicles.append(v)
 buyer=Buyer(account_id=owner,name='Синтетичний покупець',phone='0000000000',phone_normalized='0000000000');db.add(buyer);db.flush()
 order=Order(account_id=owner,number=1,buyer_id=buyer.id,contact_name=buyer.name,contact_phone=buyer.phone,contact_phone_normalized=buyer.phone_normalized,status='completed',sold_at=datetime(2026,10,20,tzinfo=timezone.utc));db.add(order);db.flush()
 entries=[];legacy=[]
 for n in range(126):
  quantity=n%4+1;price=Decimal(f'{n%9}.25');currency='USD' if n%3==0 else 'UAH'
  if n==0:quantity=2
  if n==1:price=Decimal('0');quantity=3
  if n==2:price=Decimal('12.34');quantity=2;currency='USD'
  if n==3:price=Decimal('17.05');quantity=4;currency='UAH'
  if n==4:price=Decimal('5');quantity=2;currency='USD'
  name='UI5 Синтетична деталь '+str(n)+(' із довгою назвою та уточненням установчої позиції для перевірки компактного журналу продажів' if n==125 else '')
  v=vehicles[n%2];donor=dict(manufacturer=v.manufacturer,model=v.model,year=v.year,number=v.number)
  p=Part(account_id=owner,vehicle_id=v.id,name=name,quantity=9,condition='used',selling_price=Decimal('777.77'),currency='UAH',article_number='UI5-ARTICLE-'+str(n),oem_number='UI5-OEM-'+str(n));db.add(p);db.flush()
  before=dict(name=name,article_number=p.article_number,oem_number=p.oem_number,quantity=9+quantity,selling_price='777.77');after={**before,'quantity':9}
  if n not in (0,4):after['sale']=dict(unit_price=format(price,'.2f'),total=format(price*quantity,'.2f'),currency=currency,quantity=quantity,actor_name='Історичний працівник',donor=donor,**(dict(buyer_name=buyer.name) if n==5 else {}))
  op=Operation(account_id=owner,actor_id=owner,part_id=p.id,vehicle_id=v.id,entity_id=p.id,entity_type='part',type='sale',reason='Синтетична операція UI5',before=before,after=after,created_at=datetime(2026,10,20,tzinfo=timezone.utc)+timedelta(days=n%3,seconds=n));db.add(op);db.flush()
  if n in (4,5):
   line=OrderLine(account_id=owner,order_id=order.id,part_id=p.id,name=name,donor_snapshot=donor,quantity=quantity,unit_price=Decimal('99.00'),currency=currency,line_total=Decimal('99.00')*quantity,sale_operation_id=op.id);db.add(line)
   legacy.append(dict(id=str(n),sale_operation_id=op.id,unit_price=format(price,'.2f'),currency=currency,line_total=format(price*quantity,'.2f'),donor_snapshot=donor))
  p.selling_price=Decimal('999.99') # Current price deliberately differs from the immutable sale snapshot.
  entries.append(dict(index=n,id=op.id,part_id=p.id,name=name,vehicle_id=v.id,quantity=quantity,currency=currency,unit_price=None if n==0 else format(price,'.2f'),total=None if n==0 else format(price*quantity,'.2f')))
 db.add(OrderEvent(account_id=owner,order_id=order.id,actor_id=owner,type='sale_confirmed',data={'lines':legacy,'contact_name':buyer.name}))
 for name,rights in [('reader',['sales.view','vehicles.view']),('blocked',['inventory.view','vehicles.view','catalog.view'])]:
  db.add(Account(email=f'ui5-{name}@example.test',name='UI5 '+name,password_hash=hasher.hash(f'local-ui5-{name}-password'),role='MANAGER',workspace_account_id=owner,permissions=rights))
 foreign=Account(email='ui5-other@example.test',name='UI5 Foreign Workspace',password_hash=hasher.hash('local-ui5-other-password'));db.add(foreign);db.flush()
 p=Part(account_id=foreign.id,name='UI5 FOREIGN SECRET',quantity=0);db.add(p);db.flush();db.add(Operation(account_id=foreign.id,actor_id=foreign.id,part_id=p.id,entity_id=p.id,entity_type='part',type='sale',reason='foreign synthetic',before={'quantity':1},after={'quantity':0,'name':p.name},created_at=datetime.now(timezone.utc)))
 db.commit()
 fixture=dict(synthetic=True,database='warehouse_ui5_test',owner_id=owner,entries=entries,vehicles=[dict(id=v.id,model=v.model,number=v.number) for v in vehicles],order_id=order.id,foreign_vehicle=None)
Path('/tmp/ui5-fixture.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n');print('UI5: fresh synthetic DB, 126 immutable operations, no existing databases modified')
