"""Bounded, resumable SOURCE_* SELECT-only export; explicit isolated staging upload.

Uses existing snapshot tables, contracts, and collector. No automatic DDL/publish.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from selective_import import connection
from volvo_vehicle_import import read, value, collect, import_summary, upload_snapshot
from volvo_contract import encode, digest, validate, MAX_BYTES


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encode(data))
    os.replace(temporary, path)


def verified(path):
    if path.stat().st_size > MAX_BYTES * 2:
        raise ValueError('Oversized checkpoint')
    item = json.loads(path.read_text('utf-8'))
    validate(item['payload'])
    if digest(item['payload']) != item['sha256']:
        raise ValueError('Checkpoint checksum mismatch')
    return item


def inventory(target):
    # Existing directory, no DDL or graph scans and no payload/credentials output.
    return read(target, 'SELECT car_id,model_id,sha256,coverage FROM catalogue_volvo_snapshots ORDER BY car_id')


def relation_summary(payload):
    summary = import_summary({'payload': payload, 'sha256': digest(payload)})
    pds = payload.get('details', {}).get('passanger_car_pds', [])
    linked = {r['product_id'] for r in payload['categories']}
    candidates = {int(value(r, 'productid')) for r in pds if value(r, 'productid') is not None}
    return {**summary, 'pds_only_product_ids': sorted(candidates-linked),
            'pds_only_fitment': 'needs_review', 'factory_bom': False}


def select_passenger_manufacturer(rows, manufacturer_id):
    """Pick the passenger-car role, not engine/axle/commercial-only manufacturer rows.

    TecDoc can repeat the same manufacturer ID for different data domains.
    Ambiguous or missing passenger-car roles must fail closed, not select first.
    """
    passenger = [row for row in rows if str(value(row, 'ispassengercar', '')).strip().casefold() in ('1', 'true')]
    if len(passenger) != 1:
        raise ValueError(
            f'Passenger-car manufacturer {manufacturer_id}: expected exactly one ispassengercar=True row; '
            f'found {len(passenger)} among {len(rows)} records'
        )
    return passenger[0]


def export(source, output, car_ids, model_queries, limit, mapping=None, *, graph_only=False):
    output.mkdir(parents=True, exist_ok=True)
    requested = dict(car_ids=sorted(set(car_ids)), model_queries=sorted(set(model_queries)), limit=limit,
                     mapping_sha=digest(mapping or {}), graph_only=graph_only)
    manifest_path = output/'manifest.json'
    previous = json.loads(manifest_path.read_text('utf-8')) if manifest_path.exists() else None
    if previous and previous['request'] != requested:
        raise ValueError('Checkpoint request changed; use a new output directory')
    files = dict(previous['files']) if previous else {}
    # Support only schema-inspected, fixed table names; never interpolate CLI SQL.
    tables = {value(r, 'TABLE_NAME') for r in read(source,
        'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s', ('td1q2018',))}
    car_table = 'passanger_cars' if 'passanger_cars' in tables else 'passenger_cars'
    if car_table not in tables:
        raise ValueError('Passenger modification table unavailable')
    selected = {}
    cached_ids={int(name[:-5]) for name in files if name.endswith('.json') and name[:-5].isdigit()}
    for car_id in sorted(set(car_ids)|cached_ids):
        cars = read(source, f'SELECT * FROM {car_table} WHERE id=%s', (car_id,))
        if len(cars) != 1:
            raise ValueError('Exact source modification missing')
        selected[car_id] = cars[0]
    discovery = []
    queries=sorted(set(model_queries))
    quota=max(1,(limit-len(selected))//max(1,len(queries)))
    for query in queries:
        added=0
        models = read(source, "SELECT * FROM models WHERE description LIKE %s ORDER BY id LIMIT 101", ('%'+query+'%',))
        if len(models)>100:
            raise ValueError('Model discovery cap; specify exact car IDs')
        for model in models:
            cars = read(source, f'SELECT * FROM {car_table} WHERE modelid=%s ORDER BY id LIMIT 101', (value(model,'id'),))
            # Discovery is bounded; omitted modifications are explicitly reported.
            if len(cars)>100:
                discovery.append(dict(model_id=value(model,'id'), status='discovery_truncated'))
            for car in cars[:100]:
                cid = int(value(car,'id'))
                linked = read(source, 'SELECT productid FROM article_links WHERE linkageid=%s AND linkagetypeid=2 LIMIT 1', (cid,))
                if linked:
                    discovery.append(dict(car_id=cid, model_id=value(model,'id'), description=value(car,'description'), status='source_link_available'))
                    if len(selected)<limit and added<quota and cid not in selected:
                        selected[cid]=car;added+=1
    if len(selected)>limit:
        raise ValueError('Explicit selection exceeds modification limit')
    for cid,car in sorted(selected.items()):
        models=read(source, 'SELECT * FROM models WHERE id=%s', (value(car,'modelid'),))
        if len(models)!=1:
            raise ValueError('Exact source model missing')
        model=models[0];mid=int(value(model,'manufacturerid'))
        makers=read(source, 'SELECT * FROM manufacturers WHERE id=%s', (mid,))
        maker=select_passenger_manufacturer(makers,mid)
        path=output/f'{cid}.json'
        if path.exists():
            envelope=verified(path)
            if (envelope['payload']['manufacturer_id'],envelope['payload']['model_id'],envelope['payload']['car_id']) != (mid,int(value(model,'id')),cid):
                raise ValueError('Checkpoint source identity mismatch')
            if path.name in files and files[path.name]!=file_sha(path):
                raise ValueError('Manifest checkpoint file changed')
        else:
            payload=collect(source,car,model,mapping or {},manufacturer_id=mid,graph_only=graph_only)
            payload['manufacturer']=maker
            if not payload['categories']:
                raise ValueError('No article-linked types; empty modification not exportable')
            envelope=dict(payload=payload,sha256=digest(payload))
            atomic(path,envelope)
        files[path.name]=file_sha(path)
        atomic(manifest_path,dict(schema='carpot.source.batch.v1',request=requested,files=files,
             complete=False,source_database='td1q2018',factory_bom=False))
    # PRD export is deterministic keyset pagination. Resume skips only checksum-verified full file.
    prd=output/'prd.json'
    if prd.name in files:
        if file_sha(prd)!=files[prd.name]:raise ValueError('PRD checksum mismatch')
    else:
        rows=[];after=0
        while True:
            batch=read(source, 'SELECT id,assemblygroupdescription,description,normalizeddescription,usagedescription FROM prd WHERE id>%s ORDER BY id LIMIT 1000',(after,))
            if not batch:break
            rows.extend(batch);after=int(batch[-1]['id'])
            if len(rows)>100000:raise ValueError('PRD record cap exceeded')
        atomic(prd,rows);files[prd.name]=file_sha(prd)
    manifest=dict(schema='carpot.source.batch.v1',request=requested,files=files,complete=True,
        source_database='td1q2018',factory_bom=False,discovery=discovery,
        modifications=[relation_summary(verified(output/f'{cid}.json')['payload']) for cid in sorted(selected)])
    atomic(manifest_path,manifest)
    return manifest


def validate_batch(folder, expected_sha):
    path=folder/'manifest.json'
    if file_sha(path)!=expected_sha:raise ValueError('Explicit manifest SHA-256 mismatch')
    manifest=json.loads(path.read_text('utf-8'))
    if manifest.get('schema')!='carpot.source.batch.v1' or not manifest.get('complete'):
        raise ValueError('Incomplete export')
    result=[];seen=set()
    for name,sha in manifest['files'].items():
        if name!='prd.json' and (not name.endswith('.json') or not name[:-5].isdigit()):raise ValueError('Invalid manifest path')
        if file_sha(folder/name)!=sha:raise ValueError('File checksum mismatch')
        if name=='prd.json':continue
        item=verified(folder/name);data=item['payload']
        if name!=f"{data['car_id']}.json" or data['car_id'] in seen:raise ValueError('Duplicate/mismatched modification')
        seen.add(data['car_id']);result.append(item)
    summaries={r['car_id']:r for r in manifest['modifications']}
    if seen!=set(summaries):raise ValueError('Manifest identity mismatch')
    for item in result:
        if relation_summary(item['payload'])!=summaries[item['payload']['car_id']]:raise ValueError('Manifest graph mismatch')
    return result



def review_batch(folder, expected_sha, mapping, reviewer, output):
    """Create a NEW reviewed batch; preserve original export and source IDs."""
    from volvo_review import review_taxonomy
    envelopes=validate_batch(folder,expected_sha)
    if not reviewer.strip() or output.resolve()==folder.resolve() or output.exists():
        raise ValueError('Reviewer and new output directory required')
    prepared=[]
    for item in envelopes:
        data=item['payload'];selected={}
        for row in data['categories']:
            entry=mapping.get(str(row['product_id']))
            if not entry:raise ValueError('Every exported source type requires explicit review')
            original=row.get('original') or []
            if len(original)!=1:raise ValueError('Ambiguous original PRD record')
            fields=('id','assemblygroupdescription','description','normalizeddescription','usagedescription')
            normalized={key:value(original[0],key) for key in fields}
            if entry.get('source_sha')!=digest(normalized):raise ValueError('Reviewed PRD checksum mismatch')
            selected[str(row['product_id'])]=entry
        reviewed=review_taxonomy(data,selected,reviewer)
        prepared.append(dict(payload=reviewed,sha256=digest(reviewed)))
    # All reviews validated before local files are written; no DB connections.
    manifest=json.loads((folder/'manifest.json').read_text('utf-8'))
    output.mkdir(parents=True)
    import shutil
    shutil.copyfile(folder/'prd.json',output/'prd.json')
    files={'prd.json':file_sha(output/'prd.json')}
    for item in prepared:
        path=output/f"{item['payload']['car_id']}.json"
        atomic(path,item);files[path.name]=file_sha(path)
    manifest.update(files=files,reviewed_by=reviewer,original_manifest_sha=expected_sha,
        modifications=[relation_summary(item['payload']) for item in prepared])
    atomic(output/'manifest.json',manifest)
    return dict(reviewed=len(prepared),manifest_sha256=file_sha(output/'manifest.json'))


def upload(target, envelopes):
    existing={int(r['car_id']):r for r in inventory(target)}
    # All conflicts checked BEFORE writes. Changed versions require a separate review.
    for item in envelopes:
        data=item['payload'];old=existing.get(data['car_id'])
        if old and (old['sha256']!=item['sha256'] or int(old['model_id'])!=data['model_id']):
            raise ValueError('Existing snapshot differs; explicit version review required')
        if data.get('taxonomy_status')!='reviewed':raise ValueError('Review corporate taxonomy before upload')
    uploaded=0
    for item in envelopes:
        data=item['payload']
        if data['car_id'] in existing:continue
        # Existing tables and uploader. Save directory prerequisites in SAME transaction.
        try:
            with target.cursor() as c:
                c.execute('INSERT IGNORE INTO catalogue_manufacturers (id,name_source,full_name_source) VALUES (%s,%s,%s)',
                    (data['manufacturer_id'],value(data['manufacturer'],'description'),value(data['manufacturer'],'fulldescription')))
                c.execute('INSERT IGNORE INTO catalogue_models (id,manufacturer_id,name_source,production_interval) VALUES (%s,%s,%s,%s)',
                    (data['model_id'],data['manufacturer_id'],value(data['model'],'description'),value(data['model'],'constructioninterval')))
                c.execute('SELECT manufacturer_id FROM catalogue_models WHERE id=%s FOR UPDATE',(data['model_id'],))
                if int(c.fetchone()['manufacturer_id'])!=data['manufacturer_id']:raise ValueError('Target model belongs to another manufacturer')
                c.execute('SELECT car_id FROM catalogue_volvo_snapshots WHERE car_id=%s FOR UPDATE',(data['car_id'],))
                if c.fetchone():raise ValueError('Concurrent snapshot import; retry inventory')
            upload_snapshot(target,item,approved_identity=(data['manufacturer_id'],data['model_id'],data['car_id']))
            uploaded+=1
        except Exception:
            target.rollback();raise
    return dict(uploaded=uploaded,skipped=len(envelopes)-uploaded)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['export','validate','inventory','upload','review'])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--car-id',type=int,action='append',default=[])
    p.add_argument('--discover-model',action='append',default=[])
    p.add_argument('--max-modifications',type=int,default=8)
    p.add_argument('--graph-only',action='store_true',help='Export PRD/article links without bulky per-article enrichment')
    p.add_argument('--mapping',type=Path)
    p.add_argument('--manifest-sha256')
    p.add_argument('--reviewed-by')
    p.add_argument('--review-output',type=Path)
    p.add_argument('--confirm-catalogue-staging',action='store_true')
    a=p.parse_args()
    if a.graph_only and a.mode!='export':p.error('--graph-only is only valid for export')
    if not 1<=a.max_modifications<=100 or any(i<=0 for i in a.car_id):p.error('Bounded positive identities required')
    if a.mode=='review':
        if not a.mapping or not a.reviewed_by or not a.review_output:p.error('Review requires mapping, reviewer, and NEW review-output')
        print(json.dumps(review_batch(a.output,a.manifest_sha256,json.loads(a.mapping.read_text('utf-8-sig')),a.reviewed_by,a.review_output)));return
    if a.mode in ('upload','validate'):
        envelopes=validate_batch(a.output,a.manifest_sha256)
        if a.mode=='validate':print(json.dumps(dict(valid=True,modifications=len(envelopes))));return
    if a.mode in ('inventory','upload'):
        if not a.confirm_catalogue_staging or os.getenv('DEST_HOST') not in ('127.0.0.1','localhost') or os.getenv('DEST_PORT','3306')==os.getenv('SOURCE_PORT','3306') or os.getenv('DEST_DATABASE') not in ('catalogue','railway'):
            p.error('Separate confirmed catalogue-staging localhost tunnel required')
        with connection('DEST',os.environ['DEST_DATABASE']) as target:
            if a.mode=='inventory':
                read(target,'START TRANSACTION READ ONLY');result=inventory(target);target.rollback()
                a.output.mkdir(parents=True,exist_ok=True);atomic(a.output/'staging-inventory.json',result)
            else:result=upload(target,envelopes)
        print(json.dumps(dict(mode=a.mode,rows=len(result)) if a.mode=='inventory' else result));return
    if os.getenv('SOURCE_HOST','127.0.0.1') not in ('127.0.0.1','localhost') or os.getenv('SOURCE_DATABASE','td1q2018')!='td1q2018':p.error('Only local td1q2018 source allowed')
    if not a.car_id and not a.discover_model:p.error('Specify exact source IDs or model discovery')
    a.output.mkdir(parents=True,exist_ok=True);lock=a.output/'.batch.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        with connection('SOURCE','td1q2018') as source:
            read(source,'SET SESSION max_execution_time=30000')
            read(source,'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            try:result=export(source,a.output,a.car_id,a.discover_model,a.max_modifications,json.loads(a.mapping.read_text('utf-8-sig')) if a.mapping else {},graph_only=a.graph_only)
            finally:source.rollback()
        print(json.dumps(dict(modifications=len(result['modifications']),manifest_sha256=file_sha(a.output/'manifest.json'))))
    finally:lock.unlink(missing_ok=True)


if __name__=='__main__':main()
