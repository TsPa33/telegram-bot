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



def progress(stage, **fields):
    """Opt-in, non-sensitive import diagnostics, line-buffered for PowerShell."""
    if os.getenv('CARPOT_OEM_IMPORT_TRACE') == '1':
        print('OEM_STAGE '+json.dumps({'stage':stage,**fields},ensure_ascii=False),flush=True)


def file_sha(path):
    # OEM evidence is streamed separately from the 8 MiB JSON contract.
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


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


def attach_source_oems(source, payload, sidecar_path=None):
    """Exact passenger article+manufacturer OEM references.

    For automated source export, write them as an independently checksummed
    JSONL sidecar. The canonical versioned snapshot has an 8 MiB API contract:
    embedding millions of cross-references there is neither safe nor useful.
    Existing legacy callers without a sidecar retain their previous behavior.
    """
    by_identity={(item['supplier_id'],item['article_number']):item
                 for item in payload['articles'].values()}
    keys=sorted(by_identity)
    temporary=sidecar_path.with_suffix('.tmp') if sidecar_path is not None else None
    output=temporary.open('wb') if temporary is not None else None
    count=0
    try:
        for offset in range(0,len(keys),100):
            batch=keys[offset:offset+100]
            placeholders=','.join(['(%s,%s)']*len(batch))
            args=(payload['manufacturer_id'],*(value for key in batch for value in key))
            rows=read(source,f"""SELECT supplierId,DataSupplierArticleNumber,manufacturerId,OENbr
                FROM article_oe WHERE manufacturerId=%s
                AND (supplierId,DataSupplierArticleNumber) IN ({placeholders})
                ORDER BY supplierId,DataSupplierArticleNumber,OENbr LIMIT 10001""",args)
            if len(rows)>10000:
                raise ValueError('Source OEM batch exceeds the read limit')
            expected=set(batch)
            for row in rows:
                key=(int(value(row,'supplierId')),value(row,'DataSupplierArticleNumber'))
                number=value(row,'OENbr')
                if key not in expected or not isinstance(number,str) or not number.strip():
                    continue
                if not (1<=key[0]<=65535 and isinstance(key[1],str)
                        and 1<=len(key[1])<=32 and len(number)<=64):
                    raise ValueError('Source OEM value exceeds target identity column lengths')
                if int(value(row,'manufacturerId'))!=payload['manufacturer_id']:
                    raise ValueError('OEM manufacturer does not match source modification')
                if output is not None:
                    # One line per real source reference; no silent truncation.
                    output.write(encode([key[0],key[1],payload['manufacturer_id'],number])+b'\n')
                else:
                    by_identity[key].setdefault('oem',[]).append({
                        'manufacturerId':payload['manufacturer_id'],'OENbr':number,
                        'source':'article_oe',
                    })
                count+=1
        supplier_ids=sorted({sid for sid,_ in keys})
        suppliers={}
        for offset in range(0,len(supplier_ids),100):
            batch=supplier_ids[offset:offset+100]
            rows=read(source,'SELECT id,description FROM suppliers WHERE id IN ('+
                      ','.join(['%s']*len(batch))+')',tuple(batch))
            for row in rows:
                sid=int(value(row,'id'))
                if sid in suppliers:
                    raise ValueError('Ambiguous supplier identity')
                suppliers[sid]=value(row,'description')
        for (sid,_),article in by_identity.items():
            if suppliers.get(sid):
                article['supplier']=[{'description':suppliers[sid]}]
        payload['source_scope']='passenger_prd_article_oem'
        validate(payload)
        if output is not None:
            output.close();output=None
            import os
            os.replace(temporary,sidecar_path)
        return count
    finally:
        if output is not None:
            output.close()
        if temporary is not None and temporary.exists():
            temporary.unlink()



def export(source, output, car_ids, model_queries, limit, mapping=None, *, graph_only=False, with_oem=False, omit_prd_export=False):
    output.mkdir(parents=True, exist_ok=True)
    requested = dict(car_ids=sorted(set(car_ids)), model_queries=sorted(set(model_queries)), limit=limit,
                     mapping_sha=digest(mapping or {}), graph_only=graph_only)
    if with_oem:requested['with_oem']=True
    if omit_prd_export:requested['omit_prd_export']=True
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
            if with_oem:attach_source_oems(source,payload,output/f'oem-{cid}.jsonl')
            if not payload['categories']:
                raise ValueError('No article-linked types; empty modification not exportable')
            envelope=dict(payload=payload,sha256=digest(payload))
            atomic(path,envelope)
        files[path.name]=file_sha(path)
        sidecar=output/f'oem-{cid}.jsonl'
        if with_oem and sidecar.exists():
            sidecar_sha=file_sha(sidecar)
            if sidecar.name in files and files[sidecar.name]!=sidecar_sha:
                raise ValueError('OEM sidecar checkpoint checksum mismatch')
            files[sidecar.name]=sidecar_sha
        atomic(manifest_path,dict(schema='carpot.source.batch.v1',request=requested,files=files,
             complete=False,source_database='td1q2018',factory_bom=False))
    # PRD export is deterministic keyset pagination. Resume skips only checksum-verified full file.
    prd=output/'prd.json'
    if not omit_prd_export:
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


def verified_oem_sidecar(path, payload):
    """Validate every OEM evidence row against exact fitted source article keys.

    The outer checkpoint manifest binds the file's SHA-256 and filename. Each
    record must additionally match the modification and one of its exact
    (supplier, article) identities. No cross-model/catalogue guesses.
    """
    source_keys={(r['supplier_id'],r['article_number']) for r in payload['articles'].values()}
    manufacturer=payload['manufacturer_id']
    count=0
    with path.open('rb') as stream:
        for line in stream:
            count+=1
            if count>2_000_000 or len(line)>4096:
                raise ValueError('Oversized or malformed OEM evidence sidecar')
            try:record=json.loads(line)
            except (ValueError,UnicodeDecodeError) as exc:
                raise ValueError('Invalid OEM evidence sidecar JSONL') from exc
            if (not isinstance(record,list) or len(record)!=4
                    or type(record[0]) is not int or type(record[2]) is not int
                    or record[2]!=manufacturer
                    or not isinstance(record[1],str) or not isinstance(record[3],str)
                    or not 1<=record[0]<=65535 or not 1<=len(record[1])<=32
                    or not 1<=len(record[3])<=64
                    or (record[0],record[1]) not in source_keys):
                raise ValueError('OEM sidecar reference has no exact fitted source article identity')
    return count


def fitted_oem_references(envelope):
    """Yield only exact supplier+article+manufacturer OEM keys from source."""
    payload=envelope['payload']
    sidecar=envelope.get('_oem_sidecar')
    if sidecar is not None:
        with sidecar.open('rb') as stream:
            for line in stream:
                record=json.loads(line)
                yield tuple(record)
        return
    for article in payload['articles'].values():
        for ref in article.get('oem',[]):
            number=ref.get('OENbr')
            if (ref.get('manufacturerId')==payload['manufacturer_id'] and
                    isinstance(number,str) and 0<len(number)<=64 and
                    1<=article['supplier_id']<=65535 and
                    0<len(article['article_number'])<=32):
                yield (article['supplier_id'],article['article_number'],
                       payload['manufacturer_id'],number)


def insert_fitted_parts(target,envelope,allowed_keys):
    """Create only exact source supplier/article identities required by OEM API.

    Never overwrite names or prices of already imported catalogue parts.
    """
    data=envelope['payload']
    rows=[]
    for article in data['articles'].values():
        key=(article['supplier_id'],article['article_number'])
        if key not in allowed_keys:
            continue
        sid,number=key
        if not (type(sid) is int and 1<=sid<=65535
                and isinstance(number,str) and 1<=len(number)<=32):
            raise ValueError('Invalid source article identity in catalogue parts')
        # Original catalogue article name is descriptive metadata only.
        name=article.get('name_source')
        if name is not None and not isinstance(name,str):
            name=None
        rows.append((sid,number,name[:128] if name else None))
    count=0
    progress('parts_start',car_id=data['car_id'],identities=len(rows))
    with target.cursor() as cursor:
        for offset in range(0,len(rows),250):
            count+=cursor.executemany("""INSERT IGNORE INTO catalogue_parts
                (supplier_id,article_number,name_source) VALUES (%s,%s,%s)""",
                rows[offset:offset+250])
            if offset % 2500 == 0:
                progress('parts_batch',car_id=data['car_id'],processed=min(offset+250,len(rows)),total=len(rows))
    progress('parts_done',car_id=data['car_id'],inserted=count)
    return count


def insert_fitted_oems(target,envelope,allowed_keys):
    """Idempotent batched relational upsert; caller controls commit/rollback."""
    inserted=0
    processed=0
    buffer=[]
    car_id=envelope['payload']['car_id']
    progress('oem_start',car_id=car_id)
    with target.cursor() as cursor:
        for key in fitted_oem_references(envelope):
            if (key[0],key[1]) not in allowed_keys:continue
            buffer.append(key)
            if len(buffer)>=250:
                inserted+=cursor.executemany("""INSERT IGNORE INTO catalogue_oem
                    (supplier_id,article_number,oem_manufacturer_id,oem_number)
                    VALUES (%s,%s,%s,%s)""",buffer)
                buffer.clear()
                processed+=250
                if processed % 2500 == 0:
                    progress('oem_batch',car_id=car_id,processed=processed,inserted=inserted)
        if buffer:
            inserted+=cursor.executemany("""INSERT IGNORE INTO catalogue_oem
                (supplier_id,article_number,oem_manufacturer_id,oem_number)
                VALUES (%s,%s,%s,%s)""",buffer)
            processed+=len(buffer)
    progress('oem_done',car_id=car_id,processed=processed,inserted=inserted)
    return inserted


def validate_batch(folder, expected_sha):
    path=folder/'manifest.json'
    if file_sha(path)!=expected_sha:raise ValueError('Explicit manifest SHA-256 mismatch')
    manifest=json.loads(path.read_text('utf-8'))
    if manifest.get('schema')!='carpot.source.batch.v1' or not manifest.get('complete'):
        raise ValueError('Incomplete export')
    result=[];seen=set();sidecars={}
    for name,sha in manifest['files'].items():
        is_oem=(name.startswith('oem-') and name.endswith('.jsonl')
                and name[4:-6].isdigit() and int(name[4:-6])>0)
        is_graph=name.endswith('.json') and name[:-5].isdigit()
        if name!='prd.json' and not (is_oem or is_graph):raise ValueError('Invalid manifest path')
        if file_sha(folder/name)!=sha:raise ValueError('File checksum mismatch')
        if name=='prd.json':continue
        if is_oem:
            car_id=int(name[4:-6])
            if car_id in sidecars:raise ValueError('Duplicate OEM sidecar')
            sidecars[car_id]=folder/name
            continue
        item=verified(folder/name);data=item['payload']
        if name!=f"{data['car_id']}.json" or data['car_id'] in seen:raise ValueError('Duplicate/mismatched modification')
        seen.add(data['car_id']);result.append(item)
    summaries={r['car_id']:r for r in manifest['modifications']}
    if seen!=set(summaries) or not set(sidecars).issubset(seen):raise ValueError('Manifest identity mismatch')
    for item in result:
        payload=item['payload'];car_id=payload['car_id']
        if relation_summary(payload)!=summaries[car_id]:raise ValueError('Manifest graph mismatch')
        if car_id in sidecars:
            if payload.get('source_scope')!='passenger_prd_article_oem':
                raise ValueError('OEM sidecar attached to non-OEM source graph')
            verified_oem_sidecar(sidecars[car_id],payload)
            item['_oem_sidecar']=sidecars[car_id]
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


def add_oems_to_existing_graph(target,item,old):
    """Preserve the versioned snapshot and enrich only exact shared article links."""
    data=item['payload']
    with target.cursor() as cursor:
        cursor.execute('SELECT payload FROM catalogue_volvo_versions WHERE car_id=%s AND sha256=%s',
                       (data['car_id'],old['sha256']))
        version=cursor.fetchone()
        if not version:raise ValueError('Existing snapshot version unavailable')
        current=validate(json.loads(version['payload']))
        if digest(current)!=old['sha256'] or current['manufacturer_id']!=data['manufacturer_id']:
            raise ValueError('Existing snapshot identity mismatch')
        old_links={(row['product_id'],key) for row in current['categories'] for key in row['articles']}
        new_links={(row['product_id'],key) for row in data['categories'] for key in row['articles']}
    shared_keys={key for _,key in old_links & new_links}
    allowed={(data['articles'][key]['supplier_id'],data['articles'][key]['article_number'])
             for key in shared_keys}
    progress('existing_graph_shared_links',car_id=data['car_id'],keys=len(allowed))
    insert_fitted_parts(target,item,allowed)
    inserted=insert_fitted_oems(target,item,allowed)
    target.commit()
    progress('existing_graph_committed',car_id=data['car_id'],inserted=inserted)
    return inserted,len(new_links-old_links)



def upload(target, envelopes):
    progress('inventory_start',modifications=len(envelopes))
    existing={int(r['car_id']):r for r in inventory(target)}
    progress('inventory_done',existing=len(existing))
    # All conflicts checked BEFORE writes. Changed versions require a separate review.
    for item in envelopes:
        data=item['payload'];old=existing.get(data['car_id'])
        if old and (int(old['model_id'])!=data['model_id'] or (old['sha256']!=item['sha256'] and data.get('source_scope')!='passenger_prd_article_oem')):
            raise ValueError('Existing snapshot differs; explicit version review required')
        if data.get('taxonomy_status')!='reviewed' and data.get('source_scope')!='passenger_prd_article_oem':
            raise ValueError('Review taxonomy or export a verified passenger OEM graph before upload')
    uploaded=0
    oem_inserted=0
    unpublished_links=0
    graph_import=False
    for item in envelopes:
        data=item['payload']
        old=existing.get(data['car_id'])
        graph_import |= data.get('source_scope')=='passenger_prd_article_oem'
        if old:
            progress('existing_graph_start',car_id=data['car_id'])
            if data.get('source_scope')=='passenger_prd_article_oem':
                try:
                    added,gaps=add_oems_to_existing_graph(target,item,old)
                except Exception:
                    target.rollback()
                    raise
                oem_inserted+=added
                unpublished_links+=gaps
            continue
        # Existing tables and uploader. Save directory prerequisites in SAME transaction.
        progress('new_graph_start',car_id=data['car_id'],articles=len(data['articles']))
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
            progress('snapshot_start',car_id=data['car_id'])
            upload_snapshot(target,item,approved_identity=(data['manufacturer_id'],data['model_id'],data['car_id']))
            progress('snapshot_committed',car_id=data['car_id'])
            # The source snapshot is committed before relational OEM upserts.
            # A failed upsert is safe to retry: the next run uses the existing
            # snapshot's exact-shared-link path above. INSERT IGNORE is idempotent.
            if data.get('source_scope')=='passenger_prd_article_oem':
                allowed={(a['supplier_id'],a['article_number']) for a in data['articles'].values()}
                insert_fitted_parts(target,item,allowed)
                oem_inserted+=insert_fitted_oems(target,item,allowed)
                target.commit()
                progress('new_graph_oem_committed',car_id=data['car_id'])
            uploaded+=1
        except Exception:
            target.rollback();raise
    result=dict(uploaded=uploaded,skipped=len(envelopes)-uploaded)
    if graph_import:
        result.update(existing_graph_oems_inserted=oem_inserted,existing_graph_links_pending_review=unpublished_links)
    return result


def inspect_commercial_source(source):
    """SELECT-only schema and bounded linkage sample for DAF/commercial support.

    Linkage IDs are not globally unique across source data domains. This is
    discovery, not proof that any sampled link applies to a DAF vehicle.
    """
    cols=read(source,"""SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN
          ('commercial_vehicles','commercial_vehicle_pds',
           'commercial_vehicle_attributes','commercial_vehicle_prd')
        ORDER BY TABLE_NAME,ORDINAL_POSITION""",('td1q2018',))
    groups={}
    for row in cols:
        groups.setdefault(value(row,'TABLE_NAME'),[]).append(dict(
            name=value(row,'COLUMN_NAME'),type=value(row,'DATA_TYPE')))
    sample=[]
    if any(c['name'].casefold()=='id' for c in groups.get('commercial_vehicles',[])):
        vehicles=read(source,'SELECT id FROM commercial_vehicles ORDER BY id LIMIT 8')
        for vehicle in vehicles:
            vid=int(value(vehicle,'id'))
            # A linkageid might coincide with another entity domain: no
            # commercial fitment assertion until linkage type is validated.
            link=read(source,'SELECT linkagetypeid,productid FROM article_links WHERE linkageid=%s LIMIT 40',(vid,))
            sample.append(dict(source_id=vid,observed_linkage_type_ids=sorted({
                int(value(row,'linkagetypeid')) for row in link
            }),observed_link_count_capped=len(link)))
    return dict(source_database='td1q2018',mode='commercial_preflight',
                read_only=True,commercial_fitment_verified=False,
                columns=groups,linkage_examples=sample,
                next_step='Validate commercial linkagetype and product domain; do not reuse passenger type 2 automatically')


def discover_passenger(source, after_id, scan_limit, model_id=None):
    """Keyset scan without manually supplied IDs. Source is always SELECT-only.

    Scan by the passenger modification primary key (not the huge article_links
    table), then probe the exact source relation for each candidate. The caller
    commits its checkpoint only after processing all IDs in this page.
    """
    if after_id < 0 or not 1 <= scan_limit <= 500 or (model_id is not None and model_id <= 0):
        raise ValueError('Invalid keyset position, model ID or bounded scan size')
    tables={value(r,'TABLE_NAME') for r in read(source,
        'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s',('td1q2018',))}
    table='passanger_cars' if 'passanger_cars' in tables else 'passenger_cars'
    if table not in tables:
        raise ValueError('Passenger car modification table missing')
    # Scoped first transfer can validate the real model (e.g. Volvo XC60 II
    # source model 37773) before importing the complete 68k+ passenger set.
    # Never infer exact fitment from the model alone.
    if model_id is None:
        candidates=read(source, f'SELECT id FROM {table} WHERE id>%s ORDER BY id LIMIT %s',
                        (after_id,scan_limit))
    else:
        candidates=read(source, f'SELECT id FROM {table} WHERE modelid=%s AND id>%s ORDER BY id LIMIT %s',
                        (model_id,after_id,scan_limit))
    found=[]
    for row in candidates:
        car_id=int(value(row,'id'))
        link=read(source, 'SELECT productid FROM article_links WHERE linkageid=%s AND linkagetypeid=2 LIMIT 1',(car_id,))
        if link:found.append(car_id)
    return {'mode':'discover','after_id':after_id,
            'next_after_id':int(value(candidates[-1],'id')) if candidates else after_id,
            'scanned':len(candidates),'linked_ids':found,'complete':len(candidates)<scan_limit,
            'source':'td1q2018','linkage_type':2,'model_id':model_id}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['export','validate','inventory','upload','review','discover','commercial-audit'])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--car-id',type=int,action='append',default=[])
    p.add_argument('--after-id',type=int,default=0,help='SELECT-only passenger discovery keyset cursor')
    p.add_argument('--model-id',type=int,help='Optional source model ID for scoped passenger OEM synchronization')
    p.add_argument('--scan-limit',type=int,default=50,help='Maximum passenger modifications scanned in one discovery page, 1..500')
    p.add_argument('--discover-model',action='append',default=[])
    p.add_argument('--max-modifications',type=int,default=8)
    p.add_argument('--graph-only',action='store_true',help='Export PRD/article links without bulky per-article enrichment')
    p.add_argument('--with-oem',action='store_true',help='Include exact manufacturer OEMs in graph-only export')
    p.add_argument('--omit-prd-export',action='store_true',help='For OEM graph checkpoint runs, omit redundant whole-database PRD dump')
    p.add_argument('--mapping',type=Path)
    p.add_argument('--manifest-sha256')
    p.add_argument('--reviewed-by')
    p.add_argument('--review-output',type=Path)
    p.add_argument('--confirm-catalogue-staging',action='store_true')
    p.add_argument('--target-server-uuid')
    a=p.parse_args()
    if a.with_oem and (a.mode!='export' or not a.graph_only):p.error('--with-oem requires export --graph-only')
    if a.omit_prd_export and (a.mode!='export' or not a.graph_only or not a.with_oem):p.error('--omit-prd-export requires export --graph-only --with-oem')
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
        if any(item['payload'].get('source_scope')=='passenger_prd_article_oem' for item in (envelopes if a.mode=='upload' else [])) and not a.target_server_uuid:
            p.error('Explicit staging MySQL server UUID is required for OEM graph upload')
        with connection('DEST',os.environ['DEST_DATABASE']) as target:
            if a.target_server_uuid:
                actual=read(target,'SELECT @@server_uuid AS server_uuid')[0]['server_uuid']
                if actual.casefold()!=a.target_server_uuid.casefold():
                    p.error('Target MySQL server UUID mismatch')
            if a.mode=='inventory':
                read(target,'START TRANSACTION READ ONLY');result=inventory(target);target.rollback()
                a.output.mkdir(parents=True,exist_ok=True);atomic(a.output/'staging-inventory.json',result)
            else:result=upload(target,envelopes)
        print(json.dumps(dict(mode=a.mode,rows=len(result)) if a.mode=='inventory' else result));return
    if os.getenv('SOURCE_HOST','127.0.0.1') not in ('127.0.0.1','localhost') or os.getenv('SOURCE_DATABASE','td1q2018')!='td1q2018':p.error('Only local td1q2018 source allowed')
    if a.mode=='commercial-audit':
        with connection('SOURCE','td1q2018') as source:
            read(source,'SET SESSION max_execution_time=30000')
            read(source,'START TRANSACTION READ ONLY')
            try:result=inspect_commercial_source(source)
            finally:source.rollback()
        a.output.mkdir(parents=True,exist_ok=True)
        atomic(a.output/'commercial-source-audit.json',result)
        print(json.dumps(dict(mode='commercial-audit',
                              sampled=len(result['linkage_examples']),
                              fitment_verified=False)))
        return
    if a.mode=='discover':
        if a.after_id<0 or not 1<=a.scan_limit<=500 or (a.model_id is not None and a.model_id<=0):p.error('Invalid discovery cursor/page size or model ID')
        with connection('SOURCE','td1q2018') as source:
            read(source,'SET SESSION max_execution_time=30000')
            read(source,'START TRANSACTION READ ONLY')
            try:result=discover_passenger(source,a.after_id,a.scan_limit,a.model_id)
            finally:source.rollback()
        a.output.mkdir(parents=True,exist_ok=True)
        atomic(a.output/'discovery.json',result)
        print(json.dumps(result,ensure_ascii=False));return
    if not a.car_id and not a.discover_model:p.error('Specify exact source IDs or model discovery')
    a.output.mkdir(parents=True,exist_ok=True);lock=a.output/'.batch.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        with connection('SOURCE','td1q2018') as source:
            read(source,'SET SESSION max_execution_time=30000')
            read(source,'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            try:result=export(source,a.output,a.car_id,a.discover_model,a.max_modifications,json.loads(a.mapping.read_text('utf-8-sig')) if a.mapping else {},graph_only=a.graph_only,with_oem=a.with_oem,omit_prd_export=a.omit_prd_export)
            finally:source.rollback()
        print(json.dumps(dict(modifications=len(result['modifications']),manifest_sha256=file_sha(a.output/'manifest.json'))))
    finally:lock.unlink(missing_ok=True)


if __name__=='__main__':main()
