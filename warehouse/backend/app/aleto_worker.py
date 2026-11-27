"""Run the isolated Aleto queue or administer it locally on the worker host."""
import argparse
from contextlib import closing
from datetime import UTC, datetime
import fcntl
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sqlite3
from threading import Thread
from time import sleep
from urllib.parse import urlsplit

from app.aleto_probe import SITEMAPS
from app.aleto_results import SCHEMA as EXPORT_SCHEMA, process_export
from app.services.aleto_adapter import MAX_PAGE_BYTES, extract_page
from app.services.aleto_discovery import MAX_SITEMAP_BYTES, catalogue_candidates
from app.services.aleto_source import AletoSource

MAX_JOB_PAGES = 1000
SCHEMA = """
CREATE TABLE IF NOT EXISTS parser_jobs (
    id INTEGER PRIMARY KEY, manufacturer TEXT NOT NULL, model TEXT NOT NULL,
    year INTEGER, generation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
    candidates TEXT, catalogue TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS parser_queue (
    job_id INTEGER NOT NULL REFERENCES parser_jobs(id), url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued', error TEXT, issues INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (job_id, url)
);
CREATE TABLE IF NOT EXISTS parser_progress (
    job_id INTEGER PRIMARY KEY REFERENCES parser_jobs(id),
    started_at TEXT NOT NULL, activity_at TEXT NOT NULL, current_page TEXT
);
CREATE TABLE IF NOT EXISTS market_observations (
    job_id INTEGER NOT NULL, url TEXT NOT NULL, article TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (job_id, url, article),
    FOREIGN KEY (job_id, url) REFERENCES parser_queue(job_id, url)
);
"""


def database(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript(SCHEMA + EXPORT_SCHEMA)
    return db


def select_catalogue(db, job_id, url):
    db.execute('UPDATE parser_jobs SET catalogue=?, status=?, error=NULL WHERE id=?', (url, 'queued', job_id))
    db.execute('INSERT OR IGNORE INTO parser_queue(job_id, url) VALUES (?, ?)', (job_id, url))


def discover(source, job):
    matches = set()
    for url in SITEMAPS:
        xml = source.read(url, max_bytes=MAX_SITEMAP_BYTES, allowed_types=('text/xml', 'application/xml'))
        matches.update(item.url for item in catalogue_candidates(
            xml, job['manufacturer'], job['model'], year=job['year'], generation=job['generation'],
        ))
    return sorted(matches)


def complete_discovery(db, job_id, matches):
    db.execute('BEGIN IMMEDIATE')
    current = db.execute('SELECT status FROM parser_jobs WHERE id=?', (job_id,)).fetchone()
    if current['status'] != 'queued':
        return
    status = 'needs_clarification' if matches else 'source_not_found'
    db.execute('UPDATE parser_jobs SET candidates=?, status=? WHERE id=?', (json.dumps(matches), status, job_id))
    # Slugs are candidate evidence. An operator confirms even a single result.


def within_catalogue(url, root):
    candidate = urlsplit(url)
    catalogue = urlsplit(root)
    return candidate.netloc == catalogue.netloc and candidate.path.startswith(catalogue.path.rstrip('/') + '/')


def complete_page(db, job_id, url, catalogue, result):
    db.execute('BEGIN IMMEDIATE')
    current = db.execute('SELECT status FROM parser_jobs WHERE id=?', (job_id,)).fetchone()
    if current['status'] != 'queued':
        return
    # Keep separate observations for an article seen on different listing
    # pages so inconsistent source details can be reviewed.
    db.executemany(
        'INSERT OR IGNORE INTO market_observations(job_id, url, article, payload) VALUES (?, ?, ?, ?)',
        ((job_id, url, r['source_article'], json.dumps(r, ensure_ascii=False)) for r in result['rows']),
    )
    count = db.execute('SELECT COUNT(*) FROM parser_queue WHERE job_id=?', (job_id,)).fetchone()[0]
    for link in result['links']:
        if not within_catalogue(link, catalogue):
            continue
        if count >= MAX_JOB_PAGES:
            pending = db.execute('SELECT 1 FROM parser_queue WHERE job_id=? AND url=?', (job_id, link)).fetchone()
            if pending is None:
                db.execute('UPDATE parser_jobs SET error=? WHERE id=?', ('PAGE_LIMIT', job_id))
            continue
        inserted = db.execute('INSERT OR IGNORE INTO parser_queue(job_id, url) VALUES (?, ?)', (job_id, link))
        count += inserted.rowcount
    db.execute('UPDATE parser_queue SET status=?, error=NULL, issues=? WHERE job_id=? AND url=?',
               ('done', len(result['issues']), job_id, url))


def process_one(db, source):
    job = db.execute("SELECT * FROM parser_jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
    if job is None:
        return False
    job_id = job['id']
    url = None
    stamp = datetime.now(UTC).isoformat()
    db.execute("""INSERT INTO parser_progress VALUES (?, ?, ?, NULL)
                  ON CONFLICT(job_id) DO UPDATE SET activity_at=excluded.activity_at, current_page=NULL""",
               (job_id, stamp, stamp))
    db.commit()
    try:
        if not job['catalogue']:
            complete_discovery(db, job_id, discover(source, job))
            return True
        page = db.execute(
            "SELECT url FROM parser_queue WHERE job_id=? AND status='queued' ORDER BY rowid LIMIT 1", (job_id,),
        ).fetchone()
        if page is None:
            db.execute("""UPDATE parser_jobs
                SET status=CASE WHEN error IS NOT NULL OR EXISTS (
                    SELECT 1 FROM parser_queue WHERE job_id=? AND (error IS NOT NULL OR issues>0)
                ) THEN 'partial' ELSE 'completed' END WHERE id=? AND status='queued'""", (job_id, job_id))
            return True
        url = page['url']
        db.execute('UPDATE parser_progress SET current_page=? WHERE job_id=?', (urlsplit(url).path, job_id))
        db.commit()
        html = source.read(url, max_bytes=MAX_PAGE_BYTES, allowed_types=('text/html',)).decode('utf-8-sig')
        result = extract_page(
            html, url, datetime.now(UTC).isoformat(), manufacturer=job['manufacturer'], model=job['model'],
            source='aleto', data_origin='public_html', adapter_version='oracle-worker-v1',
        )
        complete_page(db, job_id, url, job['catalogue'], result)
    except ValueError as exc:
        code = str(exc)
        if not code.isascii() or len(code) > 80 or not code.replace('_', '').isalnum():
            code = 'SOURCE_INVALID_RESPONSE'
        if url is None:
            db.execute("UPDATE parser_jobs SET status='failed', error=? WHERE id=? AND status='queued'", (code, job_id))
        else:
            # Stop the job after a blocked or failed request. Retrying requires
            # an operator and resumes from the existing queue.
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute("UPDATE parser_jobs SET status='failed', error=? WHERE id=? AND status='queued'",
                                 (code, job_id))
            if changed.rowcount:
                db.execute("UPDATE parser_queue SET status='failed', error=? WHERE job_id=? AND url=?",
                           (code, job_id, url))
    finally:
        db.execute('UPDATE parser_progress SET activity_at=?, current_page=NULL WHERE job_id=?',
                   (datetime.now(UTC).isoformat(), job_id))
    return True


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/healthz':
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}\n')


def run(db, path, port):
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with HTTPServer(('127.0.0.1', port), HealthHandler) as health:
            thread = Thread(target=health.serve_forever, daemon=True)
            thread.start()
            source = AletoSource()
            while True:
                with db:
                    worked = process_one(db, source)
                with db:
                    worked = process_export(db, path) or worked
                if not worked:
                    sleep(2)


def job_view(db, job):
    result = dict(job)
    result['candidates'] = json.loads(result['candidates'] or '[]')
    progress = db.execute('SELECT started_at, activity_at, current_page FROM parser_progress WHERE job_id=?',
                          (job['id'],)).fetchone()
    result['progress'] = dict(progress) if progress else None
    result['pages'] = dict(db.execute(
        'SELECT status, COUNT(*) FROM parser_queue WHERE job_id=? GROUP BY status', (job['id'],),
    ).fetchall())
    counts = db.execute(
        """SELECT COUNT(DISTINCT article),
                  COUNT(DISTINCT CASE WHEN json_extract(payload, '$.oem') <> '' THEN article END),
                  COUNT(DISTINCT CASE WHEN json_extract(payload, '$.price_uah') IS NOT NULL
                                         OR json_extract(payload, '$.price_usd') IS NOT NULL THEN article END)
             FROM market_observations WHERE job_id=?""",
        (job['id'],),
    ).fetchone()
    result['unique_articles'], result['with_oem'], result['with_price'] = counts
    result['page_issues'] = db.execute(
        'SELECT COALESCE(SUM(issues), 0) FROM parser_queue WHERE job_id=?', (job['id'],),
    ).fetchone()[0]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    runner = commands.add_parser('run')
    runner.add_argument('--health-port', type=int, default=8731)
    create = commands.add_parser('create')
    create.add_argument('manufacturer')
    create.add_argument('model')
    create.add_argument('--year', type=int)
    create.add_argument('--generation', default='')
    for operation in ('show', 'results', 'choose', 'pause', 'resume', 'cancel', 'retry'):
        command = commands.add_parser(operation)
        command.add_argument('id', type=int)
        if operation == 'choose':
            command.add_argument('url')
    args = parser.parse_args()

    with closing(database(args.database)) as db, db:
        if args.command == 'run':
            run(db, args.database, args.health_port)
            return
        if args.command == 'create':
            job = db.execute(
                'INSERT INTO parser_jobs(manufacturer, model, year, generation) VALUES (?, ?, ?, ?)',
                (args.manufacturer, args.model, args.year, args.generation),
            )
            print(job.lastrowid)
            return
        db.execute('BEGIN IMMEDIATE')
        job = db.execute('SELECT * FROM parser_jobs WHERE id=?', (args.id,)).fetchone()
        if job is None:
            parser.error('job not found')
        status = job['status']
        if args.command == 'show':
            print(json.dumps(job_view(db, job), ensure_ascii=False))
        elif args.command == 'results':
            for row in db.execute('SELECT payload FROM market_observations WHERE job_id=? ORDER BY rowid', (args.id,)):
                print(row['payload'])
        elif args.command == 'choose' and status == 'needs_clarification':
            if args.url not in json.loads(job['candidates']):
                parser.error('choose a URL from the job candidates')
            select_catalogue(db, args.id, args.url)
        else:
            transitions = {
                ('pause', 'queued'): 'paused',
                ('resume', 'paused'): 'queued',
                ('cancel', 'queued'): 'cancelled',
                ('cancel', 'paused'): 'cancelled',
                ('cancel', 'needs_clarification'): 'cancelled',
                ('cancel', 'failed'): 'cancelled',
                ('retry', 'failed'): 'queued',
            }
            next_status = transitions.get((args.command, status))
            if next_status is None:
                parser.error('operation is unavailable in this state')
            db.execute('UPDATE parser_jobs SET status=? WHERE id=?', (next_status, args.id))
            if args.command == 'retry':
                db.execute('UPDATE parser_jobs SET error=NULL WHERE id=?', (args.id,))
                db.execute("UPDATE parser_queue SET status='queued', error=NULL WHERE job_id=? AND status='failed'", (args.id,))


if __name__ == '__main__':
    main()
