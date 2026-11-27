"""Migrate the audited CarPot handoff into a new SQLite file."""
import argparse
from collections import Counter
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import local_store

JOIN = """SELECT m.model,m.category,m.subcategory,p.article,p.oem,p.title,p.condition,
                 p.price_uah,p.price_usd,p.url,p.checked_at,m.source_page
          FROM product_models m JOIN products p ON p.article=m.article"""
COLUMNS = ('model', 'category', 'subcategory', 'article', 'oem', 'title', 'condition',
           'price_uah', 'price_usd', 'url', 'checked_at', 'source_page')


def readonly(path):
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA trusted_schema=OFF')
    connection.execute('PRAGMA query_only=ON')
    if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        connection.close()
        raise ValueError(f'Пошкоджена база: {path.name}')
    return connection


def cells(row):
    return tuple('' if item is None else str(item) for item in row)


def reconcile(legacy, csv_path):
    expected = Counter(cells(row) for row in legacy.execute(JOIN))
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream, strict=True)
        if tuple(next(reader, [])) != COLUMNS:
            raise ValueError('Невідома структура CSV')
        actual = Counter(tuple(row) for row in reader if row)
    if actual != expected:
        raise ValueError(f'CSV і SQLite відрізняються: тільки CSV {sum((actual - expected).values())}, '
                         f'тільки SQLite {sum((expected - actual).values())}')
    return sum(expected.values())


def catalogue_root(url):
    split = urlsplit(url)
    match = re.match(r'^/(?:ua/)?car/([a-z0-9-]+)/', split.path)
    if split.scheme != 'https' or split.netloc != 'aleto.ua' or not match:
        raise ValueError('Невідома адреса каталогу')
    return f'https://aleto.ua/car/{match[1]}/'


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def import_legacy(db, legacy, csv_path):
    csv_rows = reconcile(legacy, csv_path)
    legacy_path = Path(legacy.execute('PRAGMA database_list').fetchone()[2])
    report = {'csv_rows': csv_rows, 'sha256': {
        'aleto.sqlite3': file_sha(legacy_path), 'parts.csv': file_sha(csv_path),
    }}
    for table in ('products', 'product_models', 'price_history', 'crawled_pages'):
        report[table] = legacy.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
    missing_articles = legacy.execute('''SELECT count(*) FROM products p
                                         WHERE NOT EXISTS(SELECT 1 FROM product_models m WHERE m.article=p.article)''').fetchone()[0]
    if report['product_models'] != csv_rows or missing_articles:
        raise ValueError('Виявлено зв’язки без відповідного товару')
    with db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS handoff_migration(id INTEGER PRIMARY KEY CHECK(id=1), report TEXT)')
        existing = db.execute('SELECT report FROM handoff_migration WHERE id=1').fetchone()
        if existing:
            if json.loads(existing[0])['inputs'] != report:
                raise ValueError('Робоча база вже містить інший імпорт')
            return json.loads(existing[0])
        db.execute('''CREATE TABLE legacy_price_changes (
            id INTEGER PRIMARY KEY, article TEXT NOT NULL, old_uah REAL, new_uah REAL,
            old_usd REAL, new_usd REAL, changed_at TEXT NOT NULL)''')
        db.execute('''CREATE TABLE legacy_page_audit (
            url TEXT PRIMARY KEY, model TEXT, checked_at TEXT, products_found INTEGER, error TEXT)''')
        db.executemany('INSERT INTO legacy_price_changes VALUES (?,?,?,?,?,?,?)',
                       legacy.execute('SELECT id,article,old_uah,new_uah,old_usd,new_usd,changed_at FROM price_history'))
        db.executemany('INSERT INTO legacy_page_audit VALUES (?,?,?,?,?)',
                       legacy.execute('SELECT url,model,checked_at,products_found,error FROM crawled_pages'))
        db.execute('CREATE INDEX legacy_change_article ON legacy_price_changes(article)')
        groups = {}
        for label, in legacy.execute('SELECT DISTINCT model FROM product_models ORDER BY model'):
            manufacturer, model = label.split(maxsplit=1)
            roots = {catalogue_root(row[0]) for row in legacy.execute(
                'SELECT DISTINCT source_page FROM product_models WHERE model=?', (label,),
            )}
            if len(roots) != 1:
                raise ValueError(f'Неоднозначний каталог: {label}')
            pages = legacy.execute('SELECT url, error FROM crawled_pages WHERE model=?', (label,)).fetchall()
            status = 'limited' if len(pages) >= 1000 else 'partial'
            job_id = db.execute('''INSERT INTO jobs(manufacturer,model,year,generation,catalogue,status,error,created_at)
                                   VALUES (?,?,NULL,'',?,?,?,?)''',
                                (manufacturer, model, roots.pop(), status, 'Історичний каталог моделі',
                                 datetime.now(timezone.utc).isoformat())).lastrowid
            db.executemany('INSERT INTO pages VALUES (?,?,?,?)',
                           ((job_id, row['url'], 'failed' if row['error'] else 'done', int(bool(row['error'])))
                            for row in pages))
            articles = set()
            count = 0
            for row in legacy.execute(JOIN + ' WHERE m.model=? ORDER BY m.article,m.source_page', (label,)):
                _, category, subcategory, article, oem, title, condition, uah, usd, url, stamp, page = cells(row)
                record = dict(source_article=article, part_name=title, oem=oem, condition=condition,
                              source_url=url, source_page=page, price_uah=uah, price_usd=usd,
                              category=category, subcategory=subcategory, observed_at=stamp,
                              data_origin='legacy_model_catalogue')
                db.execute('INSERT INTO parts VALUES (?,?,?,?)',
                           (job_id, page, article, json.dumps(record, ensure_ascii=False)))
                local_store.record_prices(db, job_id, record)
                articles.add(article)
                count += 1
            groups[label] = {'job_id': job_id, 'links': count, 'unique_articles': len(articles),
                             'pages': len(pages), 'status': status}
        for row in legacy.execute('SELECT * FROM price_history'):
            for label, in legacy.execute('SELECT DISTINCT model FROM product_models WHERE article=?', (row['article'],)):
                local_store.record_prices(db, groups[label]['job_id'], {
                    'source_article': row['article'], 'observed_at': row['changed_at'],
                    'price_uah': row['new_uah'], 'price_usd': row['new_usd'],
                })
        result = {'inputs': report, 'model_catalogues': groups}
        db.execute('INSERT INTO handoff_migration VALUES (1,?)', (json.dumps(result, ensure_ascii=False),))
        return result


def migrate(source, output):
    if output.exists() or output.is_symlink():
        raise FileExistsError('Файл призначення вже існує. Виберіть новий шлях.')
    loader = SourceFileLoader('aleto_migration_app', str(Path(__file__).with_name('carpot_local_aleto.pyw')))
    app = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(app)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        app.DATA_DIR = Path(temporary)
        app.DB_PATH = app.DATA_DIR / 'data.sqlite3'
        with closing(readonly(source / 'local_aleto.sqlite3')) as original, closing(sqlite3.connect(app.DB_PATH)) as copy:
            original.backup(copy)
        with closing(app.connect_db()) as db, closing(readonly(source / 'aleto.sqlite3')) as legacy:
            result = import_legacy(db, legacy, source / 'parts.csv')
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Перевірка міграції не пройдена')
        os.link(app.DB_PATH, output)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.output), ensure_ascii=False, indent=2))
