"""Read-only, resumable inventory of PRD coverage by passenger cars.

Reads only local SOURCE_* td1q2018. Stores aggregates in local SQLite, never
writes MySQL/Railway. It does not infer a factory BOM or approve canonical types.
"""
import argparse
import csv
import hashlib
import json
import os
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

from selective_import import connection


SOURCE = 'td1q2018'
TABLE_COLUMNS = {
    'manufacturers': {'id', 'description', 'ispassengercar'},
    'models': {'id', 'manufacturerid', 'description'},
    'passanger_cars': {'id', 'modelid'},
    'prd': {'id', 'description', 'normalizeddescription', 'assemblygroupdescription', 'usagedescription'},
    'article_links': {'linkageid', 'linkagetypeid', 'productid'},
}
SELECT_REFERENCES = {
    'manufacturers': 'SELECT id,description,ispassengercar FROM manufacturers',
    'models': 'SELECT id,manufacturerid,description FROM models',
    'prd': 'SELECT id,description,normalizeddescription,assemblygroupdescription,usagedescription FROM prd',
}


def truth(value):
    return str(value).strip().casefold() in ('true', '1')


def fingerprint(data):
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def index_paths(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[str(row['Key_name'])].append((int(row['Seq_in_index']), str(row['Column_name']).casefold()))
    return {name: [col for _, col in sorted(parts)] for name, parts in groups.items()}


def indexed_safely(passenger_indexes, link_indexes, prd_indexes):
    car = any(columns[:1] == ['id'] for columns in passenger_indexes.values())
    prd = any(columns[:1] == ['id'] for columns in prd_indexes.values())
    link = any(columns[:1] == ['linkageid'] or
               columns[:2] == ['linkagetypeid', 'linkageid'] for columns in link_indexes.values())
    return car and link and prd


def preflight(source):
    with source.cursor() as cur:
        cur.execute('SELECT DATABASE() AS db, VERSION() AS version')
        identity = cur.fetchone()
        if identity['db'] != SOURCE:
            raise RuntimeError('Wrong source database; only td1q2018 is allowed')
        paths = {}
        for table, required in TABLE_COLUMNS.items():
            cur.execute('SHOW COLUMNS FROM ' + table)
            available = {str(row['Field']).casefold() for row in cur.fetchall()}
            if not required <= available:
                raise RuntimeError(f'{table}: missing columns {sorted(required - available)}')
            if table in ('passanger_cars', 'article_links', 'prd'):
                cur.execute('SHOW INDEX FROM ' + table)
                paths[table] = index_paths(cur.fetchall())
    if not indexed_safely(paths['passanger_cars'], paths['article_links'], paths['prd']):
        raise RuntimeError('STOP: indexed car/PRD scan or article_links(linkageid, linkagetypeid) access not verified; no full scan started')
    return {
        'database': identity['db'], 'version': identity['version'],
        'index_access_verified': True,
        'car_index': paths['passanger_cars'],
        'article_link_index': paths['article_links'],
        'prd_index': paths['prd'],
        'source_write_operations': 0,
    }


def reference_data(source):
    result = {}
    with source.cursor() as cur:
        for name, query in SELECT_REFERENCES.items():
            cur.execute(query)
            rows = cur.fetchall()
            result[name] = sorted(rows, key=lambda r: (int(r['id']), str(r)))
    return result


def initialize(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS makers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS models (id INTEGER PRIMARY KEY, maker_id INTEGER NOT NULL, name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS prd (
        id INTEGER PRIMARY KEY, name TEXT, normalized TEXT, assembly_group TEXT, usage TEXT
    );
    CREATE TABLE IF NOT EXISTS car_scan (
        car_id INTEGER PRIMARY KEY, model_id INTEGER NOT NULL, eligible INTEGER NOT NULL, type_count INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_car_scan_model ON car_scan(model_id);
    CREATE TABLE IF NOT EXISTS model_prd (
        model_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
        PRIMARY KEY (model_id, product_id)
    );
    """)


def getmeta(db, key, default=None):
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def setmeta(db, key, value):
    db.execute('INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)', (key, str(value)))


def store_references(db, references):
    signature = fingerprint(references)
    former = getmeta(db, 'reference_sha256')
    if former is not None:
        if former != signature:
            raise RuntimeError('Source manufacturers/models/PRD changed since checkpoint; use a NEW --output directory')
        return
    if getmeta(db, 'cursor_car_id') is not None:
        raise RuntimeError('Incomplete local reference checkpoint; use a NEW --output directory')
    makers = {}
    for row in references['manufacturers']:
        if not truth(row['ispassengercar']):
            continue
        mid = int(row['id'])
        if mid in makers:
            raise RuntimeError(f'Ambiguous passenger manufacturer role for id={mid}')
        makers[mid] = row.get('description') or ''
    models = {}
    for row in references['models']:
        ident, maker = int(row['id']), int(row['manufacturerid'])
        current = (maker, row.get('description') or '')
        if ident in models and models[ident] != current:
            raise RuntimeError(f'Ambiguous model id={ident}')
        models[ident] = current
    products = {}
    for row in references['prd']:
        ident = int(row['id'])
        current = (
            row.get('description') or '', row.get('normalizeddescription') or '',
            row.get('assemblygroupdescription') or '', row.get('usagedescription') or ''
        )
        if ident in products and products[ident] != current:
            raise RuntimeError(f'Ambiguous PRD id={ident}')
        products[ident] = current
    with db:
        db.executemany('INSERT INTO makers VALUES (?,?)', sorted(makers.items()))
        db.executemany('INSERT INTO models VALUES (?,?,?)',
                       [(ident, *model) for ident, model in sorted(models.items())])
        db.executemany('INSERT INTO prd VALUES (?,?,?,?,?)',
                       [(ident, *part) for ident, part in sorted(products.items())])
        setmeta(db, 'reference_sha256', signature)
        setmeta(db, 'cursor_car_id', 0)
        setmeta(db, 'scan_complete', 0)


def read_car_batch(source, last_id, batch_size):
    with source.cursor() as cur:
        cur.execute('SELECT id,modelid FROM passanger_cars WHERE id>%s ORDER BY id LIMIT %s',
                    (last_id, batch_size))
        return cur.fetchall()


def read_type_links(source, car_ids, max_rows):
    """Indexed, bounded car IDs; deduplicate supplier/article offers to PRD types."""
    if not car_ids:
        return {}
    placeholders = ','.join(['%s'] * len(car_ids))
    sql = ('SELECT DISTINCT linkageid,productid FROM article_links '
           'WHERE linkagetypeid=2 AND linkageid IN (' + placeholders + ')')
    linked = defaultdict(set)
    count = 0
    with source.cursor() as cur:
        cur.execute(sql, tuple(car_ids))
        while True:
            records = cur.fetchmany(1000)
            if not records:
                break
            count += len(records)
            if count > max_rows:
                raise RuntimeError('Too many unique car/PRD links in one batch; rerun with --batch-size 10')
            for record in records:
                if record['productid'] is None:
                    continue
                product_id = int(record['productid'])
                if product_id > 0:
                    linked[int(record['linkageid'])].add(product_id)
    return linked


def process_batch(db, cars, linked, passenger_models):
    descriptions = []
    graph = set()
    for car in cars:
        cid, mid = int(car['id']), int(car['modelid'])
        eligible = mid in passenger_models
        parts = linked.get(cid, set()) if eligible else set()
        descriptions.append((cid, mid, int(eligible), len(parts)))
        graph.update((mid, pid) for pid in parts)
    with db:
        db.executemany('INSERT INTO car_scan VALUES (?,?,?,?)', descriptions)
        db.executemany('INSERT OR IGNORE INTO model_prd VALUES (?,?)', sorted(graph))
        setmeta(db, 'cursor_car_id', int(cars[-1]['id']))


def scan(source, db, batch_size, max_cars, max_rows):
    if getmeta(db, 'scan_complete') == '1':
        print('Previously completed; regenerating reports.', flush=True)
        return
    passenger_models = {
        row[0] for row in db.execute(
            'SELECT m.id FROM models m JOIN makers b ON b.id=m.maker_id')
    }
    position = int(getmeta(db, 'cursor_car_id', 0))
    processed = 0
    started = time.monotonic()
    while max_cars == 0 or processed < max_cars:
        n = batch_size if max_cars == 0 else min(batch_size, max_cars - processed)
        rows = read_car_batch(source, position, n)
        if not rows:
            with db:
                setmeta(db, 'scan_complete', 1)
            break
        if int(rows[0]['id']) <= position:
            raise RuntimeError('Non-advancing car-id keyset')
        eligible_ids = [int(row['id']) for row in rows if int(row['modelid']) in passenger_models]
        linked = read_type_links(source, eligible_ids, max_rows)
        process_batch(db, rows, linked, passenger_models)
        position = int(rows[-1]['id'])
        processed += len(rows)
        print(f'Scanned +{processed} cars this run; car_id={position}; '
              f'passenger cars with types in batch={sum(bool(v) for v in linked.values())}; '
              f'elapsed={time.monotonic()-started:.0f}s', flush=True)
    print('Scan complete=' + str(getmeta(db, 'scan_complete') == '1'), flush=True)


def csv_output(path, fieldnames, records):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', newline='', encoding='utf-8-sig') as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    os.replace(temporary, path)


def report(db, directory):
    if getmeta(db, 'reference_sha256') is None:
        raise RuntimeError('No reference checkpoint; run scan first')
    makers = {int(r[0]): str(r[1]) for r in db.execute('SELECT id,name FROM makers')}
    models = {int(r[0]): (int(r[1]), str(r[2]))
              for r in db.execute('SELECT id,maker_id,name FROM models')}
    model_stats = {
        int(r[0]): dict(modifications=int(r[1]), with_links=int(r[2]), car_prd_links=int(r[3]))
        for r in db.execute("""SELECT model_id,COUNT(*),SUM(type_count>0),SUM(type_count)
                              FROM car_scan WHERE eligible=1 GROUP BY model_id""")
    }
    model_types = {
        int(r[0]): int(r[1]) for r in db.execute(
            'SELECT model_id,COUNT(*) FROM model_prd GROUP BY model_id')
    }
    brand_type_counts = {
        int(r[0]): int(r[1]) for r in db.execute(
            'SELECT m.maker_id,COUNT(DISTINCT mt.product_id) '
            'FROM model_prd mt JOIN models m ON m.id=mt.model_id '
            'GROUP BY m.maker_id')
    }
    brand_known_counts = {
        int(r[0]): int(r[1]) for r in db.execute(
            'SELECT m.maker_id,COUNT(DISTINCT mt.product_id) '
            'FROM model_prd mt JOIN models m ON m.id=mt.model_id '
            'JOIN prd p ON p.id=mt.product_id GROUP BY m.maker_id')
    }
    by_brand = defaultdict(lambda: dict(models_with_cars=0, models_with_links=0,
                                        modifications=0, modifications_with_links=0, car_prd_links=0))
    by_model = []
    for mid, stats in sorted(model_stats.items()):
        maker, name = models[mid]
        record = dict(model_id=mid, model_name=name, manufacturer_id=maker,
                      manufacturer_name=makers.get(maker, ''), **stats,
                      distinct_prd_types=model_types.get(mid, 0))
        by_model.append(record)
        b = by_brand[maker]
        b['models_with_cars'] += 1
        b['models_with_links'] += int(stats['with_links'] > 0)
        for key in ('modifications', 'with_links', 'car_prd_links'):
            b['modifications_with_links' if key == 'with_links' else key] += stats[key]
    brand_rows = [
        dict(manufacturer_id=mid, manufacturer_name=makers[mid], **values,
             distinct_linked_source_ids=brand_type_counts.get(mid, 0),
             distinct_known_prd_ids=brand_known_counts.get(mid, 0))
        for mid, values in sorted(by_brand.items(), key=lambda item: (-item[1]['modifications_with_links'], item[0]))
    ]
    source_types = {
        int(row[0]): int(row[1]) for row in db.execute(
            'SELECT product_id,COUNT(*) FROM model_prd GROUP BY product_id')
    }
    prd_rows = [
        dict(product_id=row[0], source_name=row[1], normalized_name=row[2],
             assembly_group=row[3], usage=row[4],
             linked_to_passenger_models=int(source_types.get(row[0], 0)),
             linked=bool(source_types.get(row[0], 0)))
        for row in db.execute('SELECT id,name,normalized,assembly_group,usage FROM prd ORDER BY id')
    ]
    known = {row['product_id'] for row in prd_rows}
    unknown = sorted(pid for pid in source_types if pid not in known)
    completed = getmeta(db, 'scan_complete') == '1'
    summary = {
        'schema': 'carpot.source.coverage.audit.v1',
        'source_database': SOURCE,
        'complete': completed,
        'coverage_scope': 'all_passenger_car_modifications' if completed else 'scanned_prefix_only',
        'source_reference_sha256': getmeta(db, 'reference_sha256'),
        'last_scanned_car_id': int(getmeta(db, 'cursor_car_id', 0)),
        'prd_source_rows': len(prd_rows),
        'prd_source_ids_linked_to_passenger_models': sum(row['linked'] for row in prd_rows),
        'linked_ids_missing_from_prd': len(unknown),
        'car_rows_scanned': int(db.execute('SELECT COUNT(*) FROM car_scan').fetchone()[0]),
        'passenger_modifications_scanned': sum(item['modifications'] for item in brand_rows),
        'passenger_modifications_with_prd_links': sum(item['modifications_with_links'] for item in brand_rows),
        'passenger_models_with_prd_links': sum(item['models_with_links'] for item in brand_rows),
        'passenger_brands_with_prd_links': sum(item['modifications_with_links'] > 0 for item in brand_rows),
        'passenger_car_prd_link_pairs': sum(item['car_prd_links'] for item in brand_rows),
        'physical_part_types_after_normalization': None,
        'new_canonical_types_approved': 0,
        'factory_bom': False,
        'notes': [
            'PRD IDs are source taxonomy records, not unique physical part counts.',
            'Counts are distinct vehicle/PRD pairs, not unique OEM or supplier articles.',
            'No normalization, fitment review, or publication performed.',
            'Read-only source scans are not a cross-run consistent MySQL snapshot.'
        ],
    }
    csv_output(directory / 'by_brand.csv', [
        'manufacturer_id', 'manufacturer_name', 'models_with_cars',
        'models_with_links', 'modifications', 'modifications_with_links',
        'car_prd_links', 'distinct_linked_source_ids', 'distinct_known_prd_ids'
    ], brand_rows)
    csv_output(directory / 'by_model.csv', [
        'manufacturer_id', 'manufacturer_name', 'model_id', 'model_name',
        'modifications', 'with_links', 'car_prd_links', 'distinct_prd_types'
    ], by_model)
    csv_output(directory / 'prd_coverage.csv', [
        'product_id', 'source_name', 'normalized_name', 'assembly_group',
        'usage', 'linked_to_passenger_models', 'linked'
    ], prd_rows)
    csv_output(directory / 'unknown_prd_ids.csv', ['product_id'], [
        {'product_id': v} for v in unknown])
    temporary = directory / 'summary.tmp'
    temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, directory / 'summary.json')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'scan', 'report'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=50)
    parser.add_argument('--max-cars', type=int, default=0,
                        help='Cars per invocation; 0 means scan until source exhausted')
    parser.add_argument('--max-links-per-batch', type=int, default=250000)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100 or args.max_cars < 0 or args.max_links_per_batch < 1000:
        parser.error('batch-size 1..100, max-cars >= 0, max-links-per-batch >= 1000')
    args.output.mkdir(parents=True, exist_ok=True)
    if args.mode == 'report':
        if not (args.output / 'audit.sqlite3').exists():
            parser.error('No local audit.sqlite3; run scan first')
        with sqlite3.connect(args.output / 'audit.sqlite3') as db:
            report(db, args.output)
        return
    if os.getenv('SOURCE_DATABASE', SOURCE) != SOURCE or os.getenv('SOURCE_HOST', '127.0.0.1') not in ('127.0.0.1', 'localhost'):
        parser.error('Only local SOURCE_DATABASE=td1q2018 on localhost is allowed')
    with connection('SOURCE', SOURCE) as source:
        with source.cursor() as cur:
            cur.execute('SET SESSION max_execution_time=30000')
            cur.execute('SET SESSION TRANSACTION READ ONLY')
        info = preflight(source)
        print(json.dumps(info, ensure_ascii=False), flush=True)
        if args.mode == 'preflight':
            return
        lock = args.output / '.audit.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise SystemExit('Audit lock exists; confirm no other audit is running before removing')
        os.close(fd)
        try:
            with sqlite3.connect(args.output / 'audit.sqlite3') as db:
                initialize(db)
                store_references(db, reference_data(source))
                scan(source, db, args.batch_size, args.max_cars, args.max_links_per_batch)
                report(db, args.output)
        finally:
            lock.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
