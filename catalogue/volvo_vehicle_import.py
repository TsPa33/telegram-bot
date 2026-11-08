"""Windows SELECT-only Volvo export with atomic per-variant checkpoints.

Exports locally by default. --upload sends reviewed snapshots through an existing
local Railway MySQL tunnel; it never applies DDL or modifies td1q2018.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from selective_import import connection, check_space
from volvo_contract import encode, digest, validate

def value(row,key,default=None):
    return next((v for k,v in row.items() if k.casefold()==key.casefold()),default)


CAP = 20000
TABLES = ('passanger_car_attributes', 'passanger_car_trees', 'passanger_car_pds', 'passanger_car_qsi')


def read(conn, sql, args=()):
    with conn.cursor() as c:
        c.execute(sql, args)
        return c.fetchall()


def bounded(conn, table, where, args):
    # Table and predicate are internal constants, never CLI identifiers.
    rows = read(conn, f'SELECT * FROM {table} WHERE {where} LIMIT %s', (*args, CAP + 1))
    if len(rows) > CAP:
        raise ValueError(f'{table}: per-identity cap exceeded; refusing truncated snapshot')
    return rows


def collect(source, car, model, mapping):
    car_id = int(value(car,'id'))
    details = {t: bounded(source, t, 'passangercarid=%s', (car_id,)) for t in TABLES}
    links = []
    after = (0, 0, '')
    while True:
        batch = read(source, '''SELECT DISTINCT productid,supplierid,datasupplierarticlenumber
            FROM article_links WHERE linkageid=%s AND linkagetypeid=2
            AND (productid,supplierid,datasupplierarticlenumber)>(%s,%s,%s)
            ORDER BY productid,supplierid,datasupplierarticlenumber LIMIT 250''', (car_id, *after))
        if not batch:
            break
        links.extend(batch)
        if len(links) > CAP:
            raise ValueError('Article link cap exceeded')
        r = batch[-1]
        after = (r['productid'], r['supplierid'], r['datasupplierarticlenumber'])
    articles = {}
    products = {}
    artifact_bytes=len(encode(details))
    for link in links:
        sid, number, product = int(link['supplierid']), link['datasupplierarticlenumber'], int(link['productid'])
        key = f'{sid}:{number}'
        if key not in articles:
            exact = (sid, number)
            articles[key] = dict(supplier_id=sid, article_number=number,
                article=bounded(source, 'articles', 'supplierId=%s AND DataSupplierArticleNumber=%s', exact),
                supplier=bounded(source, 'suppliers', 'id=%s', (sid,)),
                oem=bounded(source, 'article_oe', 'supplierId=%s AND DataSupplierArticleNumber=%s AND manufacturerId=120', exact),
                attributes=bounded(source, 'article_attributes', 'supplierId=%s AND DataSupplierArticleNumber=%s', exact),
                images=bounded(source, 'article_images', 'supplierId=%s AND DataSupplierArticleNumber=%s', exact),
                crosses=bounded(source, 'article_cross', 'SupplierId=%s AND PartsDataSupplierArticleNumber=%s', exact),
                image_status='metadata_only', fitment='verified_source_link', car_id=car_id)
        artifact_bytes += len(encode(articles[key]))
        if artifact_bytes > 8*1024*1024:raise ValueError('Per-modification artifact byte cap exceeded')
        if product not in products:
            p = bounded(source, 'prd', 'id=%s', (product,))
            reviewed = mapping.get(str(product), {})
            products[product] = dict(product_id=product, original=p, articles=[], **reviewed)
        products[product]['articles'].append(key)
    return validate(dict(schema='carpot.volvo.v1', manufacturer_id=120, model_id=int(value(model,'id')),
        car_id=car_id, modification={**car,'id':car_id,'description':value(car,'description'),'constructioninterval':value(car,'constructioninterval')}, model=model, details=details, categories=list(products.values()),
        articles=articles, collection_complete=True, coverage='partial',
        observed_at=datetime.now(timezone.utc).isoformat(), image_status='metadata_only'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model-id', type=int, action='append', help='Exact Volvo model ID; default prioritizes XC90 II and XC60 II')
    p.add_argument('--car-id', type=int, help='Exact source modification ID, never K-Type')
    p.add_argument('--output', default='volvo-export')
    p.add_argument('--mapping', help='Reviewed product IDs -> Ukrainian 3-level taxonomy JSON')
    p.add_argument('--upload', action='store_true')
    p.add_argument('--confirm-staging', action='store_true')
    p.add_argument('--max-modifications', type=int, default=2)
    args = p.parse_args()
    if not 1 <= args.max_modifications <= 100:
        p.error('max-modifications must be 1..100')
    if os.getenv('SOURCE_HOST', '127.0.0.1') not in ('127.0.0.1', 'localhost'):
        p.error('Source must be local Windows MySQL')
    if args.upload:
        if not args.confirm_staging or os.getenv('DEST_HOST') not in ('127.0.0.1', 'localhost') or os.getenv('DEST_DATABASE') not in ('railway', 'catalogue') or os.getenv('DEST_PORT') == os.getenv('SOURCE_PORT', '3306'):
            p.error('Explicit isolated staging tunnel required')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    mapping = json.loads(Path(args.mapping).read_text('utf-8')) if args.mapping else {}
    lock=output/'.volvo-import.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)
    try:
        completed = 0
        matched_car = False
        with connection('SOURCE', 'td1q2018') as source:
            read(source, 'SET SESSION TRANSACTION READ ONLY')
            read(source, 'SET SESSION max_execution_time=30000')
            models = read(source, "SELECT * FROM models WHERE manufacturerid=120 AND ispassengercar='True' ORDER BY id")
            requested=args.model_id or [13084,37773]
            models=[m for m in models if int(value(m,'id')) in requested]
            if len(models)!=len(set(requested)):raise ValueError('Requested Volvo model missing from passenger source')
            for model in models:
                cars = bounded(source, 'passanger_cars', 'modelid=%s', (int(value(model,'id')),))
                for car in cars:
                    if args.car_id and int(value(car,'id'))!=args.car_id:continue
                    matched_car = True
                    path = output / f"{value(car,'id')}.json"
                    if path.exists():
                        old = json.loads(path.read_text('utf-8'))
                        if digest(validate(old['payload'])) != old['sha256']:
                            raise ValueError('Checkpoint checksum mismatch')
                        continue
                    payload = collect(source, car, model, mapping)
                    envelope = dict(payload=payload, sha256=digest(payload))
                    temporary = path.with_suffix('.tmp')
                    temporary.write_bytes(encode(envelope))
                    os.replace(temporary, path)
                    completed += 1
                    if completed >= args.max_modifications:
                        break
                if completed >= args.max_modifications:
                    break
        if args.car_id and not matched_car:raise ValueError('Exact Volvo source modification not found in selected models')
        if args.upload:
            with connection('DEST', os.environ['DEST_DATABASE']) as target:
                for path in sorted(output.glob('*.json')):
                    envelope = json.loads(path.read_text('utf-8'))
                    data = validate(envelope['payload'])
                    if digest(data) != envelope['sha256']:
                        raise ValueError('Export checksum mismatch')
                    check_space(target)
                    with target.cursor() as c:
                        c.execute("SET time_zone='+00:00'")
                        for item in data['articles'].values():
                            supplier=item.get('supplier',[])
                            if supplier and value(supplier[0],'description'):
                                c.execute('''INSERT INTO catalogue_suppliers(supplier_id,name_source,observed_at)
                                    VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE name_source=VALUES(name_source),observed_at=VALUES(observed_at)''',
                                    (item['supplier_id'],value(supplier[0],'description'),datetime.fromisoformat(data['observed_at']).replace(tzinfo=None)))
                        c.execute('''INSERT INTO catalogue_volvo_snapshots(car_id,model_id,payload,sha256,coverage,observed_at)
                            VALUES(%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                            payload=VALUES(payload),sha256=VALUES(sha256),coverage=VALUES(coverage),observed_at=VALUES(observed_at)''',
                            (data['car_id'], data['model_id'], encode(data).decode(), envelope['sha256'], data['coverage'],
                             datetime.fromisoformat(data['observed_at']).replace(tzinfo=None)))
                    target.commit()
        print(json.dumps(dict(exported_this_run=completed, uploaded=args.upload, live_source='local MySQL', photos='metadata_only')))
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
