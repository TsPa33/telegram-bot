"""Bounded reads and durable CSV exports for the Oracle SQLite store."""
import csv
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

COLUMNS = ('manufacturer', 'model', 'part_name', 'source_article', 'oem', 'category',
           'subcategory', 'price_uah', 'price_usd', 'condition', 'observed_at', 'source_url')
SCHEMA = """
CREATE TABLE IF NOT EXISTS parser_exports (
    id TEXT PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES parser_jobs(id),
    query TEXT NOT NULL, max_row INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued', row_count INTEGER
);
CREATE INDEX IF NOT EXISTS parser_exports_queue ON parser_exports(status);
"""


class ResultQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    q: str = Field(default='', max_length=160)
    sort: Literal['source_order', 'part_name', 'source_article', 'price_uah', 'price_usd', 'observed_at'] = 'source_order'
    direction: Literal['asc', 'desc'] = 'asc'


class ResultPage(ResultQuery):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


def matching(db, job_id, query, *, max_row=None):
    db.create_function('fold', 1, lambda value: str(value or '').casefold(), deterministic=True)
    where, args = 'job_id=?', [job_id]
    if max_row is not None:
        where += ' AND rowid<=?'
        args.append(max_row)
    if query.q:
        terms = [f"instr(fold(json_extract(payload, '$.{field}')), ?) > 0" for field in COLUMNS]
        where += ' AND (' + ' OR '.join(terms) + ')'
        args.extend([query.q.casefold()] * len(terms))
    sort = 'rowid'
    if query.sort != 'source_order':
        expression = f"json_extract(payload, '$.{query.sort}')"
        sort = f'CAST({expression} AS REAL)' if query.sort.startswith('price_') else f'fold({expression})'
    order = f'{sort} {query.direction} NULLS LAST, rowid ASC'
    return where, args, order


def queue_export(db, job_id, query):
    max_row = db.execute('SELECT COALESCE(MAX(rowid), 0) FROM market_observations WHERE job_id=?',
                         (job_id,)).fetchone()[0]
    serialized = query.model_dump_json()
    export_id = hashlib.sha256(f'{job_id}:{max_row}:{serialized}'.encode()).hexdigest()
    db.execute("""INSERT INTO parser_exports(id, job_id, query, max_row) VALUES (?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET status='queued' WHERE status='failed'""",
               (export_id, job_id, serialized, max_row))
    return export_id


def export_path(database_path, export_id):
    return Path(database_path).parent / 'exports' / (export_id + '.csv')


def csv_cell(value):
    data = '' if value is None else str(value)
    if data.lstrip()[:1] in ('=', '+', '-', '@') or data.startswith(('\t', '\r', '\n')):
        return "'" + data
    return data


def process_export(db, database_path):
    """Single parser process holds the existing worker lock; queued work survives crashes."""
    export = db.execute("SELECT * FROM parser_exports WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
    if not export:
        return False
    target = export_path(database_path, export['id'])
    temporary = target.with_suffix('.tmp')
    query = ResultQuery.model_validate_json(export['query'])
    where, args, order = matching(db, export['job_id'], query, max_row=export['max_row'])
    try:
        target.parent.mkdir(mode=0o700, exist_ok=True)
        count = 0
        with temporary.open('w', encoding='utf-8-sig', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(COLUMNS)
            for record in db.execute(f'SELECT payload FROM market_observations WHERE {where} ORDER BY {order}', args):
                row = json.loads(record['payload'])
                writer.writerow([csv_cell(row.get(field)) for field in COLUMNS])
                count += 1
        temporary.replace(target)
        db.execute("UPDATE parser_exports SET status='ready', row_count=? WHERE id=?", (count, export['id']))
    except OSError:
        temporary.unlink(missing_ok=True)
        db.execute("UPDATE parser_exports SET status='failed' WHERE id=?", (export['id'],))
    return True
