"""Windows-local, read-only schema/PRD/type-link export, reusing SOURCE_* connection.

No Railway upload, source DDL/DML, credentials output or automatic applicability inference.
"""
import argparse,hashlib,json,os,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'catalogue'))
from selective_import import connection
from volvo_vehicle_import import read,import_summary

TABLES=('prd','manufacturers','models','passanger_cars','passenger_cars','article_links','passanger_car_pds','passanger_car_trees','passanger_car_attributes')

def write(path,data):
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,default=str)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(conn,car_id):
    columns=read(conn,'SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,ORDINAL_POSITION',('td1q2018',))
    schema={}
    for r in columns:
        if r['TABLE_NAME'] in TABLES:schema.setdefault(r['TABLE_NAME'],[]).append(r)
    fks=read(conn,'SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL',('td1q2018',))
    report=dict(schema=schema,foreign_keys=[r for r in fks if r['TABLE_NAME'] in TABLES],car_id=car_id,links={},fitment_verified=False)
    sets={}
    for table,carcol,extra in [('article_links','linkageid',' AND linkagetypeid=2'),('passanger_car_pds','passangercarid','')]:
        cols={r['COLUMN_NAME'].casefold() for r in schema.get(table,[])}
        if {carcol,'productid'}<=cols and (table!='article_links' or 'linkagetypeid' in cols):
            rows=read(conn,f'SELECT productid,COUNT(*) AS records FROM `{table}` WHERE `{carcol}`=%s{extra} GROUP BY productid',(car_id,))
            sets[table]={int(r['productid']) for r in rows if r['productid'] is not None}
            report['links'][table]=dict(records=sum(int(r['records']) for r in rows),types=len(sets[table]))
        else:report['links'][table]={'status':'columns_unavailable'}
    if len(sets)==2:
        gap=sorted(sets['passanger_car_pds']-sets['article_links'])
        report['pds_only_product_ids']=gap
        # An ID in prd proves a type label exists, not vehicle fitment or physical installation.
        report['pds_only_prd']=read(conn,'SELECT id,description,normalizeddescription,assemblygroupdescription,usagedescription FROM prd WHERE id IN ('+','.join(['%s']*len(gap))+')',tuple(gap)) if gap else []
    report['tree_interpretation']='UNVERIFIED: schema/data evidence must be reviewed; tree nodes are not automatically product types'
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--car-id',type=int,default=107555);p.add_argument('--snapshot',type=Path)
    a=p.parse_args()
    if os.getenv('SOURCE_HOST','127.0.0.1') not in ('127.0.0.1','localhost') or os.getenv('SOURCE_DATABASE','td1q2018')!='td1q2018':p.error('Only localhost td1q2018 is permitted')
    if a.car_id<=0:p.error('Positive car-id required')
    if a.output.exists() and any(a.output.iterdir()):p.error('Use a new empty output directory')
    a.output.mkdir(parents=True,exist_ok=True)
    with connection('SOURCE','td1q2018') as c:
        with c.cursor() as cursor:cursor.execute('START TRANSACTION READ ONLY')
        try:
            report=collect(c,a.car_id);rows=[];after=0
            while True:
                batch=read(c,'SELECT id,assemblygroupdescription,description,normalizeddescription,usagedescription FROM prd WHERE id>%s ORDER BY id LIMIT 1000',(after,))
                if not batch:break
                rows.extend(batch);after=int(batch[-1]['id'])
                if len(rows)>100000:raise ValueError('PRD export exceeds bounded limit')
            if a.snapshot:report['existing_snapshot_summary']=import_summary(json.loads(a.snapshot.read_text(encoding='utf-8-sig')))
            hashes={'prd.json':write(a.output/'prd.json',rows),'source-audit.json':write(a.output/'source-audit.json',report)}
            write(a.output/'manifest.json',dict(exported_at=datetime.now(timezone.utc).isoformat(),database='td1q2018',read_only=True,prd_records=len(rows),files=hashes))
        finally:c.rollback()
    print('Read-only export complete; review manifest.json. No data uploaded.')
if __name__=='__main__':main()
