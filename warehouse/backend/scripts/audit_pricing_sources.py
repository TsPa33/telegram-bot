"""Read-only local source audit. Never import, publish, migrate, or create Parts."""
import os,sys,json,argparse,hashlib
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from app.models.catalogue import CatalogueOffer as Offer,CataloguePrice as Price,CatalogueJob as Job,CatalogueSource as Source,CataloguePath
from app.services.canonical_catalogue import global_inputs
from app.services.canonical_rules import classify,placement,RULE_FINGERPRINT
from app.services.price_guidance import CONDITIONS,identity,oem,AGE_DAYS
from app.services.aleto_import import BUNDLED_PACKAGE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
url=os.environ['WAREHOUSE_AUDIT_DATABASE_URL'];u=make_url(url)
if u.host not in ('localhost','127.0.0.1') or not u.database.startswith('warehouse') or not u.database.endswith('_test'):raise SystemExit('Explicit disposable/local test source only')
now=datetime.now(timezone.utc);engine=create_engine(url)
with Session(engine) as db:
 db.execute(text('SET TRANSACTION READ ONLY'))
 job=db.execute(select(Job.id,Job.file_sha256).where(Job.file_sha256==hashlib.sha256(BUNDLED_PACKAGE.read_bytes()).hexdigest(),Job.status=='applied').order_by(Job.created_at).limit(1)).first()
 if not job:raise SystemExit('No applied bundled A job; no invented coverage')
 original_rows=db.scalar(select(Job.rows).where(Job.id==job.id))
 keys=('source_article','model','category','subcategory','part_name','oem','side','position','generation','year_from','year_to')
 expected_paths={tuple(str(({**row,'category':row.get('_raw_category',row['category']),'subcategory':row.get('_raw_subcategory',row['subcategory'])}).get(k) or '') for k in keys) for row in original_rows}
 excluded_paths=0;matched_paths=0
 articles=set(db.scalars(text("SELECT DISTINCT value->>'source_article' FROM catalogue_jobs j CROSS JOIN LATERAL jsonb_array_elements(j.rows::jsonb) WHERE j.id=:id"),{'id':job.id}))
 offers=list(db.scalars(select(Offer).join(Source,Source.id==Offer.source_id).where(Source.name=='aleto',Offer.source_article.in_(articles))))
 ids={o.id for o in offers}
 latest={p.offer_id:p for p in db.scalars(select(Price).where(Price.offer_id.in_(ids),Price.observed_at<=now).distinct(Price.offer_id).order_by(Price.offer_id,Price.observed_at.desc()))}
 canonical_table=bool(db.scalar(text("SELECT to_regclass('canonical_state')")))
 canonical_sha=db.scalar(text('SELECT snapshot_sha FROM canonical_state WHERE id=1')) if canonical_table else None
 groups=defaultdict(dict);models=defaultdict(set);recognized=set();qualities=Counter()
 for record in global_inputs(db):
  if record['kind']!='v2' or record['offer_id'] not in ids:continue
  raw=record['raw'];original={**raw,'source_article':record['article'],'model':record['model'],'category':raw.get('source_category',raw['category']),'subcategory':raw.get('source_subcategory',raw['subcategory'])}
  if tuple(str(original.get(k) or '') for k in keys) not in expected_paths:excluded_paths+=1;continue
  matched_paths+=1
  match=classify(record);qualities[match['quality']]+=1
  if not match.get('type_id') or not match['quality'].startswith('verified'):continue
  pl=placement(match);recognized.add(record['offer_id']);models[record['model']].add(pl['id'])
  groups[pl['id']][(record['provider'],record['article'])]=(record,match)
 raw_by_id={o.id:o for o in offers};classification=Counter();reasons=Counter();has_any=0;cohort_sizes=Counter()
 for group in groups.values():
  cohorts=Counter();priced=False
  for record,match in group.values():
   price=latest.get(record['offer_id']);offer=raw_by_id[record['offer_id']]
   if not price:reasons['missing_or_future_observation']+=1;continue
   if price.observed_at<now-timedelta(days=AGE_DAYS):reasons['older_than_90_days']+=1;continue
   valid=[(c,v) for c,v in [('UAH',price.price_uah),('USD',price.price_usd)] if v is not None and v.is_finite() and v>0]
   if not valid:reasons['missing_price']+=1;continue
   priced=True;condition=CONDITIONS.get(identity(offer.properties.get('condition')),'unknown');code=oem(offer.properties.get('oem'))
   if not code or condition=='unknown':reasons['unknown_oem_or_condition']+=1;continue
   for currency,_ in valid:cohorts[(record['model'],record.get('generation'),code,condition,currency,json.dumps(match['features'],sort_keys=True,ensure_ascii=False))]+=1
  if priced:has_any+=1
  for count in cohorts.values():cohort_sizes['3plus' if count>=3 else '1to2']+=1
  classification['source_group_3plus' if any(n>=3 for n in cohorts.values()) else 'source_group_1to2' if cohorts else 'functional_prices_only' if priced else 'no_valid_price']+=1
 result=dict(database=u.database,read_only=True,dataset='Imported Volvo A IDs only; excludes two synthetic test.csv offers',imported_bundle_sha_verified=job.file_sha256==hashlib.sha256(BUNDLED_PACKAGE.read_bytes()).hexdigest(),as_of=now.isoformat(),policy_days=AGE_DAYS,observed_date_is_not_publication_date=True,offers=len(offers),original_import_paths=len(expected_paths),matching_import_paths=matched_paths,later_fixture_paths_excluded=excluded_paths,source_paths=db.scalar(select(__import__('sqlalchemy').func.count()).select_from(CataloguePath).where(CataloguePath.offer_id.in_(ids))),unknown_condition_offers=sum(CONDITIONS.get(identity(o.properties.get('condition')),'unknown')=='unknown' for o in offers),canonical_tables_present=canonical_table,published_snapshot=canonical_sha,active_canonical_guidance_coverage=None if not canonical_sha else 'Requires authorized Part/configuration-specific evaluation; no assumptions inserted',offline_unpublished_rule_diagnostic=dict(not_published=True,not_Part_price_recommendations=True,rules_sha=RULE_FINGERPRINT,recognized_offers=len(recognized),unrecognized_offers=len(offers)-len(recognized),potential_placements=len(groups),placements_with_any_valid_quote=has_any,source_group_buckets=dict(classification),source_cohorts=dict(cohort_sizes),model_placement_counts={m:len(v) for m,v in models.items()},exclusion_counts=dict(reasons),path_quality_counts=dict(qualities)))
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False))
engine.dispose()
