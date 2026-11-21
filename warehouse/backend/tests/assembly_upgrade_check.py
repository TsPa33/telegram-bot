"""Explicit local empty-DB parent→head evidence; never runs during pytest collection."""
import os,subprocess,json,sys
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
url=os.environ['WAREHOUSE_ASSEMBLY_MIGRATION_TEST_URL']
parsed=make_url(url)
if parsed.drivername!='postgresql+psycopg' or parsed.host!='127.0.0.1' or parsed.port!=55441 or not (parsed.database or '').startswith('warehouse_assembly_upgrade') or not parsed.database.endswith('_test'):
 raise RuntimeError('Dedicated local assembly upgrade test database required')
with create_engine(url).connect() as check:
 if check.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar():
  raise RuntimeError('Only a new empty dedicated test database may be initialized')
os.environ['WAREHOUSE_DATABASE_URL']=url
env=dict(os.environ)
def migrate(rev):subprocess.run([sys.executable,'-m','alembic','upgrade',rev],env=env,check=True)
migrate('e641b3a20f97')
from app.models import Account,Vehicle,Part,Operation,Buyer,Order,OrderLine
engine=create_engine(url)
with Session(engine) as db:
 a=Account(email='migration-synthetic@example.test',name='Local synthetic',password_hash='not-a-real-password');db.add(a);db.flush()
 v=Vehicle(account_id=a.id,manufacturer='Synthetic',model='Preserved donor',year=2018,number=1,donor_id='MIGRATION-ONLY');db.add(v);db.flush()
 p=Part(account_id=a.id,vehicle_id=v.id,name='Existing stock',quantity=5,reserved_quantity=2,selling_price='123.45',currency='USD');db.add(p);db.flush()
 db.add(Operation(account_id=a.id,actor_id=a.id,part_id=p.id,vehicle_id=v.id,entity_id=p.id,entity_type='parts',type='receipt',reason='Synthetic preserved history',before={'quantity':0},after={'quantity':5}));
 b=Buyer(account_id=a.id,name='Synthetic buyer',phone='0501234567',phone_normalized='380501234567');db.add(b);db.flush()
 o=Order(account_id=a.id,number=1,buyer_id=b.id,contact_name=b.name,contact_phone=b.phone,contact_phone_normalized=b.phone_normalized);db.add(o);db.flush()
 db.add(OrderLine(account_id=a.id,order_id=o.id,part_id=p.id,name=p.name,donor_snapshot={},quantity=1,unit_price='12.34',currency='USD',line_total='12.34'))
 db.execute(text("INSERT INTO dismantling_items (id,account_id,vehicle_id,source,included,catalog_key,category_key,category_name,subcategory_key,subcategory_name,name,position,status,quantity,created_at,plan_v3) VALUES ('migration-existing-node',:a,:v,'synthetic',true,'existing','body','Body','door','Door','Existing plan','','unchecked',1,now(),'{}')"),{'a':a.id,'v':v.id})
 db.commit()
tables=['vehicles','parts','operations','buyers','orders','order_lines','dismantling_items']
def state():
 with engine.connect() as db:return {t:db.execute(text(f'SELECT row_to_json(r) FROM {t} r ORDER BY id')).scalars().all() for t in tables}
before=state();migrate('head');after=state()
for t in tables:
 assert len(before[t])==len(after[t])
 for old,new in zip(before[t],after[t]):assert old=={k:new[k] for k in old},t
assert after['dismantling_items'][0]['assembly_completeness'] is None
with engine.connect() as db:
 assert db.execute(text('SELECT count(*) FROM assembly_memberships')).scalar()==0
 assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='f7a10b8c43d2'
print(json.dumps({'status':'PASS','from':'e641b3a20f97','to':'f7a10b8c43d2','preserved_tables':tables,'quantity':5,'reserved':2,'price':'123.45','currency':'USD','new_memberships':0}))
