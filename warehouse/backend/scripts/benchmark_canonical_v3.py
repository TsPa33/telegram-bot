"""Synthetic v3 scale check. Destructive only in a disposable loopback *_test DB."""
import os,sys,json,time,resource,argparse,hashlib
from pathlib import Path
from types import SimpleNamespace
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-disposable',action='store_true',required=True);p.parse_args()
from sqlalchemy.engine import make_url
url=os.environ.get('WAREHOUSE_TEST_DATABASE_URL','');u=make_url(url)
if u.host not in ('127.0.0.1','localhost') or not u.database.startswith('warehouse') or not u.database.endswith('_test'):raise SystemExit('Disposable loopback warehouse*_test only')
os.environ['WAREHOUSE_DATABASE_URL']=url
from sqlalchemy import select,func,text,inspect
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Account,Session as AuthSession,now
from app.models.catalogue import CatalogueJob,CatalogueOffer,CatalogueApplication,CataloguePath
from app.models.canonical import CanonicalRun,CanonicalType,CanonicalPlacement,CanonicalVariant,CanonicalMapping
from app.services.catalogue_format import ImportRow,digest
from app.services.catalogue_import import preview,apply
from app.services.canonical_jobs import enqueue,process_one
with engine().begin() as conn:
 conn.execute(text('TRUNCATE accounts,catalogue_sources,catalogue_entities,catalogue_state,canonical_types,canonical_runs,canonical_state CASCADE'))
 conn.execute(text('INSERT INTO catalogue_state VALUES (1,0)'))
 conn.execute(text("INSERT INTO canonical_state VALUES (1,NULL,'{}'::json)"))
rows=[]
for i in range(29922):
 app=i%14324;article=app%10222;bucket=i//14324
 title=['Генератор Volvo T5','Стартер Volvo','Фара передня ліва Volvo LED','Противотуманная фара правая Volvo LED','Невідомий блок XY'+str(article)][article%5]
 rows.append(ImportRow.model_validate(dict(schema_version='2',source='aleto',source_article='SYNTH-'+str(article),manufacturer='Volvo',model='XC40' if app<10222 else ['XC60','XC90'][app%2],
  category='Електрика',subcategory='Підкатегорія '+str(article%5)+'-'+str(bucket),part_name=title,oem='SYNTH-OEM-'+str(article%50),price_uah='100.00',source_url='https://aleto.ua/ua/detail/synthetic-v3/',observed_at='2026-10-28T12:00:00+00:00')).model_dump())
with Session(engine()) as db:
 actor=Account(email='v3-scale@example.test',name='Synthetic v3 scale',password_hash='not-a-login');db.add(actor);db.flush();aid=actor.id
 auth=AuthSession(token_hash='a'*64,csrf_hash='b'*64,account_id=aid,expires_at=now()+timedelta(hours=1));db.add(auth)
 job=CatalogueJob(actor_id=aid,filename='SYNTHETIC-V3.csv',file_sha256='0'*64,payload_sha256=digest(rows),rows=rows,format='v2-csv');db.add(job);db.commit();jid=job.id
os.environ['WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS']=aid
with Session(engine()) as db:j=preview(db,jid,aid,{});token=j.preview_token;assert j.status=='ready';db.commit()
with Session(engine()) as db:apply(db,jid,aid,token);db.commit()
with Session(engine()) as db:
 assert [db.scalar(select(func.count()).select_from(c)) for c in (CatalogueOffer,CatalogueApplication,CataloguePath)]==[10222,14324,29922]
def fingerprint():
 with Session(engine()) as db:
  return {table:hashlib.sha256(json.dumps(sorted(json.dumps(dict(r),sort_keys=True,default=str) for r in db.execute(text('SELECT * FROM "'+table+'"')).mappings())).encode()).hexdigest() for table in inspect(db.bind).get_table_names() if not table.startswith('canonical_')}
before=fingerprint();del rows
who=SimpleNamespace(actor_id=aid,session=SimpleNamespace(token_hash='a'*64))
def execute(mode,previous=None):
 with Session(engine()) as db:
  r=enqueue(db,who,mode,previous.id if previous else None,previous.token if previous else None);db.commit();rid=r.id
 start=time.perf_counter();process_one(engine());elapsed=time.perf_counter()-start
 with Session(engine(),expire_on_commit=False) as db:
  r=db.get(CanonicalRun,rid);assert r.status=='done',r.error;db.expunge(r)
 return r,round(elapsed,3)
preview_run,ps=execute('preview');published,aps=execute('publish',preview_run)
with Session(engine()) as db:counts={c.__tablename__:db.scalar(select(func.count()).select_from(c)) for c in (CanonicalType,CanonicalPlacement,CanonicalVariant,CanonicalMapping)}
repeat,rps=execute('preview');_,ras=execute('publish',repeat)
with Session(engine()) as db:assert counts=={c.__tablename__:db.scalar(select(func.count()).select_from(c)) for c in (CanonicalType,CanonicalPlacement,CanonicalVariant,CanonicalMapping)}
assert before==fingerprint()
print(json.dumps(dict(synthetic=True,real_staging_B_tested=False,offers=10222,applications=14324,paths=29922,preview_seconds=ps,publish_seconds=aps,repeat_preview_seconds=rps,repeat_publish_seconds=ras,peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),report={k:v for k,v in published.report.items() if k!='issues'},stored=counts,old_tables_unchanged=True,repeat_no_new_reference_records=True),ensure_ascii=False,indent=2))
