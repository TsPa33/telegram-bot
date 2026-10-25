"""Opt-in measured benchmark on a disposable *_test DB; no production fixture."""
import os,time,json,statistics,tracemalloc,resource,sys
from subprocess import run
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import insert,event,text
from app.models import Part
from app.db import engine

pytestmark=pytest.mark.skipif(os.getenv('WAREHOUSE_SMART_PERF')!='1',reason='Opt-in 100k local benchmark')

def test_scale(logged,vehicle):
    account=logged.get('/api/v1/auth/me').json()['id'];measurements=[];size=0
    sql_count=[0];captured=[];points=[]
    def sql(conn,cursor,statement,parameters,context,many):
        sql_count[0]+=1
        if 'count(' in statement.lower() and 'parts' in statement.lower():captured.append((statement,parameters))
        if 'EXISTS' in statement.upper() and 'parts' in statement:points.append((statement,parameters))
    for target in (1000,10000,100000):
        start=time.perf_counter()
        with engine().begin() as db:
            for offset in range(size,target,2000):
                batch=[]
                for i in range(offset,min(target,offset+2000)):
                    name=['Радіатор охолодження','Бампер передній','Капот','Задній ліхтар правий','Блок керування двигуном'][i%5]
                    batch.append({'id':str(uuid4()),'account_id':account,'vehicle_id':vehicle['id'],'name':f'{name} {i}',
                        'quantity':1,'reserved_quantity':0,'availability':'present','oem_number':f'OEM-{i:07d}',
                        'article_number':f'ART-{i:07d}','selling_price':'123.45','currency':'UAH'})
                db.execute(insert(Part),batch)
            db.execute(text('ANALYZE parts'));db.execute(text('ANALYZE vehicles'))
        load_ms=(time.perf_counter()-start)*1000;size=target
        event.listen(engine(),'before_cursor_execute',sql)
        timings=[];counts=[];results=[];query_counts=[];points.clear();tracemalloc.start()
        for query in [f'OEM-{target-1:07d}','радік','капотт','ка','мозги мотора','правий задній ліхтар','лівий задній ліхтар','передній бампер','задній бампер','радіаторт охолоджентя']:
            samples=[];statuses=[];totals=[]
            for _ in range(3):
                sql_count[0]=0;started=time.perf_counter()
                r=logged.get('/api/v1/smart-search/parts',params={'q':query,'in_stock':True,'limit':20})
                elapsed=(time.perf_counter()-started)*1000
                assert r.status_code in (200,503),(target,query,r.text)
                statuses.append(r.status_code)
                if r.status_code==503:
                    assert target==100000 and query.startswith('OEM-') is False
                    assert r.json()['detail']=='Пошук перевищив ліміт часу. Уточніть запит.'
                    totals.append(None)
                else:
                    assert len(r.json()['items'])<=20
                    if query in ('лівий задній ліхтар','задній бампер'):assert r.json()['total']==0
                    else:assert r.json()['total']>0
                    totals.append(r.json()['total'])
                samples.append(elapsed);counts.append(sql_count[0]);timings.append(elapsed)
            query_counts.append((query,*captured[-1]))
            results.append({'q':query,'median_ms':round(statistics.median(samples),2),'total_samples':totals,'http_statuses':statuses})
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop();event.remove(engine(),'before_cursor_execute',sql)
        # This benchmark records bounded 503 timeouts explicitly; they are NOT successful searches.
        # Real planner, no enable_seqscan=off. The rare exact OEM must use its index.
        with engine().connect() as db:
            plan=db.execute(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT id FROM parts WHERE NOT archived AND account_id=:a AND oem_number<>'' AND warehouse_search_code(oem_number)=:q"),{'a':account,'q':f'oem{target-1:07d}'}).scalar_one()
            fts=db.execute(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT id FROM parts WHERE NOT archived AND account_id=:a AND to_tsvector('simple',warehouse_search_text(name)) @@ to_tsquery('simple','likhtar:* & prav:*')"),{'a':account}).scalar_one()
            index_bytes=db.scalar(text("SELECT pg_indexes_size('parts')"))
            db.execute(text("SET LOCAL jit = off"))
            statement,parameters=captured[-1]
            actual_plan=db.exec_driver_sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+statement,parameters).scalar_one()
            query_plans=[]
            for query,statement,parameters in query_counts:
                query_plans.append({'q':query,'plan':db.exec_driver_sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+statement,parameters).scalar_one()})
            statement,parameters=points[0]
            point_plan=db.exec_driver_sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+statement,parameters).scalar_one()
        assert 'ix_parts_smart_oem_number' in json.dumps(plan)
        # Page boundaries are stable across repeated requests against unchanged rows.
        one=logged.get('/api/v1/smart-search/parts',params={'q':'радік','limit':20}).json()
        two=logged.get('/api/v1/smart-search/parts',params={'q':'радік','limit':20,'offset':20}).json()
        repeat=logged.get('/api/v1/smart-search/parts',params={'q':'радік','limit':20}).json()
        assert [x['id'] for x in one['items']]==[x['id'] for x in repeat['items']]
        assert not ({x['id'] for x in one['items']}&{x['id'] for x in two['items']})
        measurements.append({'parts':target,'load_ms':round(load_ms,2),'query_samples':results,
            'p50_ms':round(statistics.median(timings),2),'max_ms':round(max(timings),2),'max_sql_queries_including_auth':max(counts),
            'peak_python_bytes':peak,'process_max_rss_kib_including_fixture':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'parts_index_bytes':index_bytes,'query_count_plans':query_plans,'oem_plan':plan,'fts_plan':fts,'actual_count_plan':actual_plan,'identifier_preflight_plan':point_plan})
        print('PERF',target,json.dumps({k:v for k,v in measurements[-1].items() if k not in ('query_count_plans','oem_plan','fts_plan','actual_count_plan','identifier_preflight_plan')},ensure_ascii=False),flush=True)
    checksum="SELECT count(*),sum(quantity),sum(reserved_quantity),sum(hashtextextended(row_to_json(p)::text,0)::numeric) FROM parts p"
    with engine().connect() as db:before=tuple(db.execute(text(checksum)).one())
    run([sys.executable,'-m','alembic','downgrade','d86f21a90b34'],check=True)
    started=time.perf_counter();run([sys.executable,'-m','alembic','upgrade','head'],check=True)
    upgrade_ms=(time.perf_counter()-started)*1000
    with engine().connect() as db:assert tuple(db.execute(text(checksum)).one())==before
    measurements[-1]['populated_100k_migration_ms']=round(upgrade_ms,2)
    print('100K MIGRATION PRESERVED ALL ROW CHECKSUMS',round(upgrade_ms,2),'ms',flush=True)
    output=Path(os.environ.get('WAREHOUSE_SMART_PERF_OUTPUT','/tmp/warehouse-ux57-perf.json'));output.write_text(json.dumps(measurements,ensure_ascii=False,indent=2))
