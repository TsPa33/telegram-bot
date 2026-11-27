"""Additive storage for the existing Local Aleto database."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4


def migrate(db, path, *, fresh=False):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (0, 11):
        raise ValueError('Непідтримувана версія локальної бази')
    if version == 11:
        return
    db.execute('BEGIN IMMEDIATE')
    try:
        if db.execute('PRAGMA user_version').fetchone()[0] == 11:
            db.commit()
            return
        if not fresh:
            backup = Path(path).with_name(f'local_aleto-before-v11-{uuid4().hex}.sqlite3')
            with sqlite3.connect(backup) as target, sqlite3.connect(path) as source:
                source.backup(target)
        for statement in (
            """CREATE TABLE vehicles (
                id INTEGER PRIMARY KEY, manufacturer TEXT NOT NULL, model TEXT NOT NULL, year INTEGER,
                generation TEXT NOT NULL DEFAULT '', vin TEXT, modification TEXT, engine TEXT, displacement TEXT,
                fuel TEXT, drive TEXT, transmission TEXT, source_modification_id INTEGER,
                source TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
            'CREATE UNIQUE INDEX vehicles_vin ON vehicles(vin) WHERE vin IS NOT NULL',
            'ALTER TABLE jobs ADD COLUMN vehicle_id INTEGER REFERENCES vehicles(id)',
            'CREATE INDEX jobs_vehicle ON jobs(vehicle_id)',
            """CREATE TABLE price_history (
                job_id INTEGER NOT NULL REFERENCES jobs(id), article TEXT NOT NULL,
                observed_at TEXT NOT NULL, currency TEXT NOT NULL, price TEXT NOT NULL,
                PRIMARY KEY(job_id,article,observed_at,currency,price))""",
            """INSERT OR IGNORE INTO price_history
                SELECT job_id,article,json_extract(payload,'$.observed_at'),'UAH',json_extract(payload,'$.price_uah')
                FROM parts WHERE json_valid(payload) AND json_extract(payload,'$.observed_at') <> ''
                AND json_extract(payload,'$.price_uah') <> ''""",
            """INSERT OR IGNORE INTO price_history
                SELECT job_id,article,json_extract(payload,'$.observed_at'),'USD',json_extract(payload,'$.price_usd')
                FROM parts WHERE json_valid(payload) AND json_extract(payload,'$.observed_at') <> ''
                AND json_extract(payload,'$.price_usd') <> ''""",
            'PRAGMA user_version=11',
        ):
            db.execute(statement)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def add_vehicle(db, manufacturer, model, year, generation, *, vin=None, source='manual', **details):
    timestamp = datetime.now(timezone.utc).isoformat()
    fields = ('modification', 'engine', 'displacement', 'fuel', 'drive', 'transmission')
    if vin:
        saved = db.execute('SELECT id FROM vehicles WHERE vin=?', (vin,)).fetchone()
        if saved:
            return saved[0]
    return db.execute(
        """INSERT INTO vehicles(manufacturer,model,year,generation,vin,modification,engine,displacement,
                                fuel,drive,transmission,source,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (manufacturer, model, year, generation, vin, *(details.get(field) for field in fields),
         source, timestamp, timestamp),
    ).lastrowid


def record_prices(db, job_id, record):
    for currency in ('UAH', 'USD'):
        price = record.get('price_' + currency.lower())
        if price not in (None, ''):
            db.execute('INSERT OR IGNORE INTO price_history VALUES (?,?,?,?,?)',
                       (job_id, record['source_article'], record['observed_at'], currency, price))


def search(db, job_id, term='', category='', has_oem=False, has_price=False, price_order=False, offset=0):
    db.create_function('casefold', 1, lambda value: (value or '').casefold(), deterministic=True)
    fields = ('source_article', 'part_name', 'oem')
    search_fields = ' OR '.join(f"instr(casefold(json_extract(payload,'$.{field}')),?)>0" for field in fields)
    conditions = ['job_id=?', 'json_valid(payload)']
    values = [job_id]
    if term.strip():
        conditions.append('(' + search_fields + ')')
        values.extend([term.strip().casefold()] * len(fields))
    if category.strip():
        conditions.append("instr(casefold(json_extract(payload,'$.category')),?)>0")
        values.append(category.strip().casefold())
    if has_oem:
        conditions.append("json_extract(payload,'$.oem')<>''")
    if has_price:
        conditions.append("(json_extract(payload,'$.price_uah')<>'' OR json_extract(payload,'$.price_usd')<>'')")
    order = "CAST(NULLIF(json_extract(payload,'$.price_uah'),'') AS REAL) ASC NULLS LAST,rowid" if price_order else 'rowid DESC'
    return db.execute(
        f"SELECT payload FROM parts WHERE {' AND '.join(conditions)} ORDER BY {order} LIMIT 101 OFFSET ?",
        (*values, offset),
    ).fetchall()


def import_v1(db, path):
    """Merge the documented v1.0.0 schema from a closed app's SQLite copy."""
    from contextlib import closing
    import json
    import shutil
    from tempfile import TemporaryDirectory

    path = Path(path)
    with TemporaryDirectory(prefix='carpot-import-') as directory:
        copy = Path(directory) / 'source.sqlite3'
        shutil.copyfile(path, copy)
        for suffix in ('-wal', '-journal'):
            sidecar = path.with_name(path.name + suffix)
            if sidecar.is_file():
                shutil.copyfile(sidecar, copy.with_name(copy.name + suffix))
        with closing(sqlite3.connect(copy)) as source:
            source.row_factory = sqlite3.Row
            source.execute('PRAGMA trusted_schema=OFF')
            source.execute('PRAGMA query_only=ON')
            expected = {
                'jobs': {'id', 'manufacturer', 'model', 'year', 'generation', 'catalogue', 'status', 'error', 'created_at'},
                'pages': {'job_id', 'url', 'status', 'errors'},
                'parts': {'job_id', 'page', 'article', 'payload'},
            }
            for table, columns in expected.items():
                actual = {row[0] for row in source.execute('SELECT name FROM pragma_table_info(?)', (table,))}
                if actual != columns:
                    raise ValueError('Схема джерела відрізняється від SQLite CarPot Local Aleto v1.0.0')
            with db:
                db.execute('BEGIN IMMEDIATE')
                inserted = 0
                for job in source.execute('SELECT * FROM jobs ORDER BY id'):
                    fields = tuple(job[field] for field in ('manufacturer', 'model', 'year', 'generation', 'catalogue', 'created_at'))
                    existing = db.execute('''SELECT id FROM jobs WHERE manufacturer=? AND model=? AND year IS ?
                                             AND generation=? AND catalogue=? AND created_at=? ORDER BY id LIMIT 1''',
                                          fields).fetchone()
                    job_id = existing[0] if existing else db.execute(
                        '''INSERT INTO jobs(manufacturer,model,year,generation,catalogue,created_at,status,error)
                           VALUES (?,?,?,?,?,?,?,?)''', (*fields, job['status'], job['error']),
                    ).lastrowid
                    db.executemany('INSERT OR IGNORE INTO pages VALUES (?,?,?,?)', (
                        (job_id, page['url'], page['status'], page['errors'])
                        for page in source.execute('SELECT * FROM pages WHERE job_id=?', (job['id'],))
                    ))
                    for part in source.execute('SELECT * FROM parts WHERE job_id=?', (job['id'],)):
                        record = json.loads(part['payload'])
                        if not isinstance(record, dict) or record.get('source_article') != part['article']:
                            raise ValueError('Запис джерела пошкоджено')
                        record_prices(db, job_id, record)
                        inserted += db.execute('INSERT OR IGNORE INTO parts VALUES (?,?,?,?)', (
                            job_id, part['page'], part['article'], part['payload'],
                        )).rowcount
            return inserted
