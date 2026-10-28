"""Destructive LOCAL disposable PostgreSQL benchmark; synthetic data, never staging."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rows',type=int,choices=[1000,10000,29922,30000,50000],required=True)
parser.add_argument('--confirm-disposable',action='store_true',required=True)
args=parser.parse_args()
url=os.environ.get('WAREHOUSE_TEST_DATABASE_URL','')
from sqlalchemy.engine import make_url
parsed=make_url(url)
if parsed.host not in ('127.0.0.1','localhost') or not parsed.database.startswith('warehouse') or not parsed.database.endswith('_test'):
    raise SystemExit('Only loopback warehouse*_test database is permitted')
os.environ['WAREHOUSE_DATABASE_URL']=url
from sqlalchemy import text,event,select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Account
from app.models.catalogue import CatalogueJob as Job,CatalogueOffer as Offer,CatalogueApplication as Application,CataloguePath as CPath
from app.services.catalogue_format import ImportRow,digest
from app.services.catalogue_import import preview,apply
with engine().begin() as conn:
    conn.execute(text('TRUNCATE accounts,catalogue_sources,catalogue_entities,catalogue_state CASCADE'))
    conn.execute(text('INSERT INTO catalogue_state VALUES (1,0)'))
n=args.rows;offers=round(n*10222/29922);applications=round(n*14324/29922)
rows=[]
for i in range(n):
    app=i%applications;article=str(app%offers);bucket=i//applications
    r=dict(schema_version='2',source='aleto',source_article=article,manufacturer='Volvo',
        model='XC40' if app<offers else ['XC60','XC90'][app%2],category='Категорія '+str(app%12),
        subcategory='Підкатегорія '+str(bucket)+'-'+str(app%20),part_name='Синтетична деталь '+article,
        oem='SYNTHETIC-'+article,condition='SYNTHETIC ONLY',price_uah=str(100+int(article)%20000)+'.00',
        source_url='https://aleto.ua/ua/detail/synthetic-benchmark/',observed_at='2026-10-28T12:00:00+00:00')
    rows.append(ImportRow.model_validate(r).model_dump())
with Session(engine()) as db:
    actor=Account(email='benchmark@example.test',name='Synthetic benchmark',password_hash='not-a-login');db.add(actor);db.flush();aid=actor.id
    job=Job(actor_id=aid,filename='synthetic-benchmark.csv',file_sha256='0'*64,payload_sha256=digest(rows),rows=rows,format='v2-csv');db.add(job);db.commit();jid=job.id
del rows
import gc
gc.collect()
calls={'sql':0,'flush':0}
def query(*a):calls['sql']+=1
def flush(*a):calls['flush']+=1
event.listen(engine(),'before_cursor_execute',query);event.listen(Session,'after_flush',flush)
result={'synthetic':True,'input_rows':n,'input_offers':offers,'input_applications':applications,'timings':{}}
def measure(name,callback):
    before=dict(calls);start=time.perf_counter()
    with Session(engine()) as db:
        job=callback(db);db.commit();report=dict(job.report);token=job.preview_token
    result['timings'][name]={'seconds':round(time.perf_counter()-start,3),**{k:calls[k]-before[k] for k in calls}}
    print(name,result['timings'][name],file=sys.stderr,flush=True)
    return report,token
report,token=measure('preview',lambda db:preview(db,jid,aid,{}))
again,token=measure('repeat_preview',lambda db:preview(db,jid,aid,{}));assert report==again
with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Offer))==0
measure('apply',lambda db:apply(db,jid,aid,token))
measure('repeat_apply',lambda db:apply(db,jid,aid,token))
with Session(engine()) as db:
    result['stored']={cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in (Offer,Application,CPath)}
assert list(result['stored'].values())==[offers,applications,n],result
result['peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1)
print(json.dumps(result,ensure_ascii=False,indent=2))
