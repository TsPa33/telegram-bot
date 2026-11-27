"""Private Oracle control API. Serve behind authenticated TLS from Warehouse."""
from contextlib import closing
from datetime import UTC, datetime
from time import time
import hmac
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.aleto_results import ResultPage, ResultQuery, export_path, matching, queue_export
from app.aleto_worker import database, job_view, select_catalogue

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
SCHEMA = """
CREATE TABLE IF NOT EXISTS parser_access (
    job_id INTEGER PRIMARY KEY REFERENCES parser_jobs(id), workspace TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parser_refresh (
    job_id INTEGER PRIMARY KEY REFERENCES parser_jobs(id),
    latest_job_id INTEGER NOT NULL REFERENCES parser_jobs(id),
    due_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS parser_audit (
    id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES parser_jobs(id),
    actor TEXT NOT NULL, action TEXT NOT NULL, occurred_at TEXT NOT NULL
);
"""
TRANSITIONS = {
    ('pause', 'queued'): 'paused', ('resume', 'paused'): 'queued',
    ('cancel', 'queued'): 'cancelled', ('cancel', 'paused'): 'cancelled',
    ('cancel', 'needs_clarification'): 'cancelled', ('retry', 'failed'): 'queued',
}


class Vehicle(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    manufacturer: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    generation: str = Field(default='', max_length=100)
    year: int | None = Field(default=None, ge=1886, le=2100)


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['choose', 'pause', 'resume', 'cancel', 'retry', 'refresh', 'schedule', 'unschedule']
    url: str | None = Field(default=None, max_length=2000)


def authorized(authorization: str = Header(default='')):
    token = os.environ.get('CARPOT_ALETO_TOKEN', '')
    if len(token) < 32 or not hmac.compare_digest(authorization.encode(), ('Bearer ' + token).encode()):
        raise HTTPException(401, 'Unauthorized')


def connection():
    path = os.environ.get('CARPOT_ALETO_DATABASE')
    if not path:
        raise HTTPException(503, 'Worker database is unavailable')
    db = database(Path(path))
    db.executescript(SCHEMA)
    return db


def audit(db, job_id, actor, action):
    db.execute('INSERT INTO parser_audit(job_id, actor, action, occurred_at) VALUES (?, ?, ?, ?)',
               (job_id, actor, action, datetime.now(UTC).isoformat()))


def owned(db, job_id, workspace):
    job = db.execute("""SELECT j.* FROM parser_jobs j JOIN parser_access a ON a.job_id=j.id
                       WHERE j.id=? AND a.workspace=?""", (job_id, workspace)).fetchone()
    if job is None:
        raise HTTPException(404, 'Завдання відсутнє')
    return job


def refresh_job(db, job_id, workspace, actor):
    new_id = db.execute("""INSERT INTO parser_jobs(manufacturer, model, year, generation, catalogue, candidates)
                         SELECT manufacturer, model, year, generation, catalogue, candidates
                         FROM parser_jobs WHERE id=?""", (job_id,)).lastrowid
    db.execute('INSERT INTO parser_access VALUES (?, ?)', (new_id, workspace))
    db.execute("""INSERT INTO parser_queue(job_id, url)
                  SELECT ?, url FROM parser_queue WHERE job_id=? ORDER BY rowid""", (new_id, job_id))
    audit(db, new_id, actor, 'create_refresh')
    audit(db, job_id, actor, 'refresh')
    return new_id


def enqueue_due():
    with closing(connection()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        now = int(time())
        item = db.execute("""SELECT s.job_id, s.latest_job_id, a.workspace, j.status FROM parser_refresh s
                            JOIN parser_access a ON a.job_id=s.job_id JOIN parser_jobs j ON j.id=s.latest_job_id
                            WHERE s.due_at<=? AND j.status IN ('completed','partial','cancelled')
                            ORDER BY s.due_at LIMIT 1""", (now,)).fetchone()
        if item:
            new_id = refresh_job(db, item['latest_job_id'], item['workspace'], 'scheduler')
            db.execute('UPDATE parser_refresh SET latest_job_id=?, due_at=? WHERE job_id=?',
                       (new_id, now + 86400, item['job_id']))


def view(db, job):
    value = job_view(db, job)
    value['scheduled'] = db.execute('SELECT 1 FROM parser_refresh WHERE job_id=?', (job['id'],)).fetchone() is not None
    return value


@app.get('/jobs', dependencies=[Depends(authorized)])
def history(x_workspace: str = Header(max_length=100)):
    with closing(connection()) as db:
        jobs = db.execute("""SELECT j.* FROM parser_jobs j JOIN parser_access a ON a.job_id=j.id
                             WHERE a.workspace=? ORDER BY j.id DESC LIMIT 30""", (x_workspace,))
        return {'items': [view(db, job) for job in jobs]}


@app.post('/jobs', dependencies=[Depends(authorized)])
def create(data: Vehicle, x_workspace: str = Header(max_length=100), x_actor: str = Header(max_length=100)):
    with closing(connection()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("""SELECT COUNT(*) FROM parser_jobs j JOIN parser_access a ON a.job_id=j.id
                         WHERE a.workspace=? AND j.status IN ('queued','paused','needs_clarification')""",
                      (x_workspace,)).fetchone()[0] >= 10:
            raise HTTPException(409, 'Забагато відкритих завдань')
        job_id = db.execute('INSERT INTO parser_jobs(manufacturer, model, year, generation) VALUES (?, ?, ?, ?)',
                            (data.manufacturer, data.model, data.year, data.generation)).lastrowid
        db.execute('INSERT INTO parser_access VALUES (?, ?)', (job_id, x_workspace))
        audit(db, job_id, x_actor, 'create')
        return view(db, owned(db, job_id, x_workspace))


@app.post('/jobs/{job_id}/command', dependencies=[Depends(authorized)])
def command(job_id: int, data: Command, x_workspace: str = Header(max_length=100), x_actor: str = Header(max_length=100)):
    with closing(connection()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        job = owned(db, job_id, x_workspace)
        status = job['status']
        if data.action == 'choose' and status == 'needs_clarification':
            if data.url not in json.loads(job['candidates']):
                raise HTTPException(422, 'Виберіть один із кандидатів')
            select_catalogue(db, job_id, data.url)
        elif data.action == 'refresh' and status in ('completed', 'partial'):
            new_id = refresh_job(db, job_id, x_workspace, x_actor)
            return view(db, owned(db, new_id, x_workspace))
        elif data.action == 'schedule' and status == 'completed':
            db.execute('INSERT OR IGNORE INTO parser_refresh VALUES (?, ?, ?)',
                       (job_id, job_id, int(time()) + 86400))
        elif data.action == 'unschedule':
            db.execute('DELETE FROM parser_refresh WHERE job_id=?', (job_id,))
        else:
            target = TRANSITIONS.get((data.action, status))
            if not target:
                raise HTTPException(409, 'Дія недоступна для цього стану')
            db.execute('UPDATE parser_jobs SET status=?, error=NULL WHERE id=?', (target, job_id))
            if data.action == 'retry':
                db.execute("UPDATE parser_queue SET status='queued', error=NULL WHERE job_id=? AND status='failed'",
                           (job_id,))
        audit(db, job_id, x_actor, data.action)
        return view(db, owned(db, job_id, x_workspace))


@app.get('/jobs/{job_id}/results', dependencies=[Depends(authorized)])
def results(job_id: int, x_workspace: str = Header(max_length=100),
            x_actor: str = Header(max_length=100), query: ResultPage = Query()):
    offset, limit = query.offset, query.limit
    with closing(connection()) as db, db:
        job = owned(db, job_id, x_workspace)
        audit(db, job_id, x_actor, 'results')
        where, args, order = matching(db, job_id, query)
        records = db.execute(f'SELECT payload FROM market_observations WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?',
                             (*args, limit + 1, offset)).fetchall()
        return {'items': [json.loads(row['payload']) for row in records[:limit]], 'status': job['status'],
                'next_offset': offset + limit if len(records) > limit else None}


@app.get('/jobs/{job_id}/import-page', dependencies=[Depends(authorized)])
def import_page(job_id: int, x_workspace: str = Header(max_length=100), after: int = Query(0, ge=0)):
    with closing(connection()) as db:
        job = owned(db, job_id, x_workspace)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Завдання ще не завершено')
        rows = db.execute("""SELECT rowid, payload FROM market_observations
                             WHERE job_id=? AND rowid>? ORDER BY rowid LIMIT 501""",
                          (job_id, after)).fetchall()
        return {'items': [{'id': row['rowid'], 'row': json.loads(row['payload'])} for row in rows[:500]],
                'done': len(rows) <= 500}


@app.post('/jobs/{job_id}/exports', dependencies=[Depends(authorized)], status_code=202)
def request_export(job_id: int, data: ResultQuery, x_workspace: str = Header(max_length=100),
                   x_actor: str = Header(max_length=100)):
    with closing(connection()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        owned(db, job_id, x_workspace)
        export_id = queue_export(db, job_id, data)
        audit(db, job_id, x_actor, 'export')
        return {'id': export_id}


@app.get('/jobs/{job_id}/exports/{export_id}', dependencies=[Depends(authorized)])
@app.get('/jobs/{job_id}/exports/{export_id}/download', dependencies=[Depends(authorized)])
def get_export(job_id: int, export_id: str, request: Request, x_workspace: str = Header(max_length=100)):
    with closing(connection()) as db:
        owned(db, job_id, x_workspace)
        row = db.execute('SELECT id, status, row_count FROM parser_exports WHERE id=? AND job_id=?',
                         (export_id, job_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Експорт відсутній')
        if not request.url.path.endswith('/download'):
            return dict(row)
        path = export_path(os.environ['CARPOT_ALETO_DATABASE'], row['id'])
        if row['status'] != 'ready' or not path.is_file():
            raise HTTPException(409, 'Експорт ще недоступний')
        return FileResponse(path, media_type='text/csv', filename=f'aleto-{job_id}.csv')


if __name__ == '__main__':
    enqueue_due()
