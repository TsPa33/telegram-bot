"""Synthetic complete DB-backed plan benchmark; destructive ONLY to explicit loopback *_test DB."""
import argparse,os,sys,time,json,resource,cProfile,pstats,io
from pathlib import Path
from types import SimpleNamespace
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-disposable',action='store_true',required=True);p.add_argument('--sizes',nargs='+',type=int,default=[100,500,1000,5000]);p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',action='store_true');args=p.parse_args()
from sqlalchemy.engine import make_url
url=os.environ.get('WAREHOUSE_TEST_DATABASE_URL','');u=make_url(url)
if u.host not in ('127.0.0.1','localhost') or not (u.database or '').startswith('warehouse') or not u.database.endswith('_test'):raise SystemExit('Explicit disposable loopback warehouse*_test required')
os.environ['WAREHOUSE_DATABASE_URL']=url;os.environ['WAREHOUSE_CATALOGUE_WORKER_ENABLED']='false'
from sqlalchemy import text,select,insert,event,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Account,Session as AuthSession,Vehicle,DismantlingItem,Part,Operation,now
from app.models.catalogue import CatalogueSource,CatalogueEntity,CatalogueOffer,CatalogueApplication,CataloguePath
from app.models.canonical import CanonicalState,CanonicalType,CanonicalPlacement,CanonicalVariant,CanonicalMapping
from app.services.canonical_rules import sid,type_record,classify,surface,installation_for,placement,variant,RULE_FINGERPRINT,TYPES
from app.services.canonical_catalogue import global_inputs
from app.services.catalogue_format import digest
from app.services.aleto_import import identity
from app.services import dismantling_plan_v3 as service
from app.schemas.dismantling_v3 import PlanPreview,PlanSave,PlanDecision
from uuid import uuid4
E=engine();report={'profile_enabled':args.profile,'synthetic':True,'real_B_tested':False,'fixture':'N distinct constructive slots, preverified synthetic canonical mapping; NOT a normalization/real fitment claim','cases':[]}
def write():args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def bulk(db,cls,rows):
 for start in range(0,len(rows),300):db.execute(insert(cls).values(rows[start:start+300]))
def seed(n):
 if not 33<=n<=10000:raise ValueError('33..10000 only')
 with E.begin() as c:
  c.execute(text('TRUNCATE accounts,catalogue_sources,catalogue_entities,catalogue_state,canonical_types,canonical_runs,canonical_state CASCADE'))
  c.execute(text('INSERT INTO catalogue_state(id,revision) VALUES(1,1)'));c.execute(text("INSERT INTO canonical_state(id,snapshot_sha,policy) VALUES(1,NULL,'{}'::json)"))
 with Session(E) as db:
  actor=Account(email='managed-stress@example.test',name='Synthetic stress fixture',password_hash='not-a-login');db.add(actor);db.flush();aid=actor.id
  db.add(AuthSession(token_hash='a'*64,csrf_hash='b'*64,account_id=aid,expires_at=now()+timedelta(days=1)))
  v=Vehicle(account_id=aid,manufacturer='Volvo',model='XC90',year=2020,number=1,donor_id='SYNTHETIC-STRESS',acquisition_date=date(2026,1,1),acquisition_cost=0);db.add(v);db.flush();vid=v.id
  src=sid('stress-source');brand=sid('stress-brand');model=sid('stress-model')
  db.add(CatalogueSource(id=src,name='synthetic-stress'))
  for id,kind,name,parent in [(brand,'manufacturer','Volvo',None),(model,'model','XC90',brand)]:
   db.add(CatalogueEntity(id=id,kind=kind,name=name,parent_id=parent,parent_kind='manufacturer' if parent else None,normalized_name=identity(name),identity_key=digest([kind,name]),details={}));db.flush()
  offers=[];applications=[];paths=[];custom={}
  for i in range(n-33):
   title=f'Тестовий конструктивний вузол {i:05d}';t=type_record(title,'Тестова конструкція','Окремі функції',{'synthetic_stress':True});custom[title]=t
   oid=sid('stress-offer',i);properties=dict(part_name=title,oem='SYNTHETIC-OEM-'+str(i),condition='synthetic',source_url='https://example.invalid/synthetic')
   offers.append(dict(id=oid,source_id=src,source_article='SYNTHETIC-'+str(i),properties=properties,observed_at=now()))
   applications.append(dict(offer_id=oid,model_id=model,model_kind='model'))
   paths.append(dict(id=sid('stress-path',i),offer_id=oid,model_id=model,path_key=digest(i),part_type_id=None,part_kind=None,raw=dict(category='Тестова конструкція',subcategory='Окремі функції',side='',position='')))
  bulk(db,CatalogueOffer,offers);bulk(db,CatalogueApplication,applications);bulk(db,CataloguePath,paths);db.flush()
  types={};placements={};variants={};mappings=[];sha=digest(['synthetic-stress-plan',n])
  for source in global_inputs(db):
   if source['kind']=='base':outcome=classify(source);t=TYPES[outcome['type_id']]
   else:
    t=custom[source['title']];parsed=surface(source);outcome=dict(type_id=t['id'],quality='verified_owner',installation=installation_for(parsed),features=parsed['features'],evidence={'normalization':parsed,'synthetic_stress':True})
   types[t['id']]=t;p=placement(outcome);placements[p['id']]=p;vref=None
   if source['kind']=='v2':vref=variant(source,outcome,p);variants[vref['id']]=vref
   mappings.append(dict(id=sid('stress-mapping',sha,source['key']),snapshot_sha=sha,source_kind=source['kind'],source_key=source['key'],source_sha=source['sha'],catalogue_path_id=source.get('path_id'),type_id=t['id'],placement_id=p['id'],variant_id=vref['id'] if vref else None,quality=outcome['quality'],evidence={**outcome['evidence'],'normalization':outcome['evidence']['normalization'],'resolved_installation':outcome['installation'],'resolved_features':outcome['features']}))
  bulk(db,CanonicalType,list(types.values()));bulk(db,CanonicalPlacement,list(placements.values()));bulk(db,CanonicalVariant,list(variants.values()));bulk(db,CanonicalMapping,mappings)
  state=db.get(CanonicalState,1);state.snapshot_sha=sha;state.policy={'rules_sha':RULE_FINGERPRINT,'alias_ids':[]};db.commit()
 return aid,vid

def measure(name,fn):
 counts={'sql':0,'flushes':0}
 def sql(*a,**kw):counts['sql']+=1
 def flush(*a,**kw):counts['flushes']+=1
 event.listen(E,'before_cursor_execute',sql);event.listen(Session,'before_flush',flush)
 profiler=cProfile.Profile() if args.profile else None
 start=time.perf_counter()
 if profiler:profiler.enable()
 try:value=fn()
 finally:
  if profiler:
   profiler.disable();stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumtime').print_stats(18);args.output.with_suffix(f'.{CURRENT}-{name}.profile.txt').write_text(stream.getvalue())
  event.remove(E,'before_cursor_execute',sql);event.remove(Session,'before_flush',flush)
 result={**counts,'seconds':round(time.perf_counter()-start,3),'peak_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1)}
 print(json.dumps({'size':CURRENT,'operation':name,**result}),flush=True)
 return value,result

def context(aid,vid):
 db=Session(E);actor=db.get(Account,aid);auth=db.get(AuthSession,'a'*64);v=db.get(Vehicle,vid);db.info['actor_id']=aid
 return db,v,SimpleNamespace(actor_id=aid,workspace_account_id=aid,user=actor,session=auth)
def prepare(aid,vid):
 db,v,who=context(aid,vid)
 try:return service.make_preview(db,v,who,PlanPreview(facts=[]))
 finally:db.close()
def apply_plan(aid,vid,plan,key):
 db,v,who=context(aid,vid)
 try:
  db.execute(select(Vehicle).where(Vehicle.id==vid).with_for_update())
  result=service.save(db,v,who,PlanSave(facts=[],token=plan['token'],request_key=key,confirm=True));db.commit();return result
 finally:db.close()
for CURRENT in args.sizes:
 aid,vid=seed(CURRENT);case={'positions':CURRENT};print(f'START {CURRENT}',flush=True)
 plan,case['preview']=measure('preview',lambda:prepare(aid,vid));assert plan['counts']['proposed']==CURRENT and plan['counts']['review']==0
 saved,case['save']=measure('save',lambda:apply_plan(aid,vid,plan,str(uuid4())))
 repeat,case['repeat_preview']=measure('repeat-preview',lambda:prepare(aid,vid));assert repeat['counts']['existing']==CURRENT
 _,case['repeat_save']=measure('repeat-save',lambda:apply_plan(aid,vid,repeat,str(uuid4())))
 db,v,who=context(aid,vid)
 try:
  ids=list(db.scalars(select(DismantlingItem.id).where(DismantlingItem.vehicle_id==vid).order_by(DismantlingItem.id).limit(1000)));etag=service.state(db,v)
 finally:db.close()
 def exclude():
  db,v,who=context(aid,vid)
  try:
   result=service.decide(db,v,who,PlanDecision(ids=ids,action='exclude',reason='Synthetic explicit bulk review',etag=etag,request_key=str(uuid4())));db.commit();return result
  finally:db.close()
 case['bulk_exclude_positions']=len(ids)
 _,case['bulk_exclude']=measure('bulk-exclude',exclude)
 with Session(E) as db:
  assert db.scalar(select(func.count()).select_from(DismantlingItem))==CURRENT
  assert db.scalar(select(func.count()).select_from(Part))==0
  assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='dismantling_v3_bind'))==2*CURRENT
  assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='dismantling_v3_decision'))==len(ids)
  case['no_stock_created']=True;case['repeat_no_duplicates']=True
 report['cases'].append(case);write()
