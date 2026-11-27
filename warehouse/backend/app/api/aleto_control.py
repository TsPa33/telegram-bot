"""Warehouse owner gateway for the isolated Aleto worker."""
import json
import os
import re
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from app.aleto_control import Command, Vehicle
from app.aleto_results import ResultPage, ResultQuery
from app.api.catalogue import Admin, Auth, DB
from app.api.secure_route import SecureRoute
from app.models.catalogue import CatalogueJob
from app.services.catalogue_format import ImportRow, digest
from app.schemas import VinClarifications
from app.services import vin_resolution
from app.services.unified_catalogue import CatalogueAdapter
from app.services.vin_lookup import lookup

router = APIRouter(prefix='/api/v1/admin/aleto-worker', route_class=SecureRoute)


class VinInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    vin: str = Field(max_length=40)


def worker_request(who, path):
    base = os.environ.get('WAREHOUSE_ALETO_WORKER_URL', '').rstrip('/')
    token = os.environ.get('WAREHOUSE_ALETO_WORKER_TOKEN', '')
    url = urlsplit(base)
    if (len(token) < 32 or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.scheme != 'https'):
        raise HTTPException(503, 'Aleto Worker ще не підключено')
    headers = {'Authorization': 'Bearer ' + token, 'X-Workspace': str(who.workspace_account_id),
               'X-Actor': str(who.actor_id)}
    return base + path, headers


def worker(who, method, path, payload=None):
    url, headers = worker_request(who, path)
    try:
        response = httpx.request(method, url, json=payload, headers=headers,
                                 timeout=10, follow_redirects=False, trust_env=False)
        if response.status_code in (404, 409, 422):
            raise HTTPException(response.status_code, 'Дію відхилено. Оновіть стан завдання.')
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'Aleto Worker недоступний') from None


@router.post('/vin')
def resolve(data: VinInput, who: Auth):
    vin = data.vin.strip().upper()
    if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', vin):
        raise HTTPException(422, 'VIN має складатися з 17 символів без I, O, Q')
    decoded = lookup(vin, public_only=True)
    vehicle = decoded['vehicle']
    status = 'NEEDS_CLARIFICATION' if vehicle.get('manufacturer') or vehicle.get('model') else 'NOT_IDENTIFIED'
    oracle = {'status': 'manufacturer_required', 'items': []}
    if vehicle.get('manufacturer'):
        try:
            context = vin_resolution.trusted_context(vin_resolution.issue_context(decoded, who), who)
            match = vin_resolution.search(CatalogueAdapter(), context, VinClarifications(), who)
            oracle = {
                'status': match['status'],
                'items': [{key: item[key] for key in ('manufacturer', 'model', 'modification',
                                                      'source_modification_id', 'matches')}
                          for item in match['items']],
            }
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            oracle['status'] = 'unavailable'
    return {'status': status, 'vehicle': vehicle, 'oracle': oracle,
            'conflicts': decoded['conflicts'], 'consistency_issues': decoded['consistency_issues']}


@router.get('/jobs')
def history(who: Auth):
    return worker(who, 'GET', '/jobs')


@router.post('/jobs')
def create(data: Vehicle, who: Auth):
    return worker(who, 'POST', '/jobs', data.model_dump())


@router.post('/jobs/{job_id}/command')
def command(job_id: int, data: Command, who: Auth):
    return worker(who, 'POST', f'/jobs/{job_id}/command', data.model_dump())


@router.get('/jobs/{job_id}/results')
def results(job_id: int, who: Auth, query: ResultPage = Query()):
    params = urlencode(query.model_dump())
    return worker(who, 'GET', f'/jobs/{job_id}/results?{params}')


@router.post('/jobs/{job_id}/exports', status_code=202)
def request_export(job_id: int, data: ResultQuery, who: Auth):
    return worker(who, 'POST', f'/jobs/{job_id}/exports', data.model_dump())


@router.get('/jobs/{job_id}/exports/{export_id}')
def export_status(job_id: int, who: Auth, export_id: str = Path(pattern=r'^[a-f0-9]{64}$')):
    return worker(who, 'GET', f'/jobs/{job_id}/exports/{export_id}')


@router.get('/jobs/{job_id}/exports/{export_id}/download')
def download_export(job_id: int, who: Auth, export_id: str = Path(pattern=r'^[a-f0-9]{64}$')):
    url, headers = worker_request(who, f'/jobs/{job_id}/exports/{export_id}/download')
    client = httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
    try:
        response = client.send(client.build_request('GET', url, headers=headers), stream=True)
        if response.status_code != 200:
            status = response.status_code
            response.close()
            raise HTTPException(status if status in (404, 409) else 502, 'Експорт недоступний')
    except BaseException as exc:
        client.close()
        if isinstance(exc, httpx.HTTPError):
            raise HTTPException(502, 'Aleto Worker недоступний') from None
        raise

    def stream():
        try:
            yield from response.iter_bytes()
        finally:
            response.close()
            client.close()

    return StreamingResponse(stream(), media_type='text/csv', headers={
        'Content-Disposition': f'attachment; filename="aleto-{job_id}.csv"',
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
    })


class PrepareBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cursor: int = Field(ge=0)


def scope(who, job_id):
    if os.environ.get('RAILWAY_ENVIRONMENT_NAME') != 'warehouse-staging':
        raise HTTPException(403, 'Імпорт Aleto доступний у Warehouse staging')
    return {'actor': who.actor_id, 'job': job_id}


RUN = ('SELECT cursor, seen, rejected, done FROM aleto_import_runs '
       'WHERE actor_id=:actor AND job_id=:job')
EMPTY = {'cursor': 0, 'seen': 0, 'rejected': 0, 'done': False}


@router.get('/jobs/{job_id}/prepare')
def import_report(job_id: int, db: DB, who: Auth, owner: Admin, offset: int = Query(0, ge=0)):
    params = scope(who, job_id)
    run = db.execute(text(RUN), params).mappings().first()
    rows = db.execute(text("""
        SELECT b.start_cursor, b.end_cursor, b.catalogue_job_id, b.entries, j.status
        FROM aleto_import_batches b LEFT JOIN catalogue_jobs j ON j.id=b.catalogue_job_id
        WHERE b.actor_id=:actor AND b.job_id=:job ORDER BY b.start_cursor LIMIT 11 OFFSET :offset
    """), {**params, 'offset': offset}).mappings().all()
    return {**(dict(run) if run else EMPTY), 'batches': [dict(row) for row in rows[:10]],
            'next_offset': offset + 10 if len(rows) > 10 else None}


@router.post('/jobs/{job_id}/prepare')
def prepare(job_id: int, data: PrepareBatch, db: DB, who: Auth, owner: Admin):
    params = scope(who, job_id)
    db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
               {'key': f'aleto-import:{params["actor"]}:{job_id}'})
    found = db.execute(text(RUN), params).mappings().first()
    run = dict(found) if found else dict(EMPTY)
    if run['cursor'] != data.cursor or run['done']:
        return run
    result = worker(who, 'GET', f'/jobs/{job_id}/import-page?after={data.cursor}')
    items = result['items']
    if len(items) > 500 or (not items and not result['done']):
        raise HTTPException(502, 'Некоректний пакет Aleto')
    rows, entries = [], []
    cursor = data.cursor
    for item in items:
        if type(item['id']) is not int or item['id'] <= cursor:
            raise HTTPException(502, 'Некоректний курсор Aleto')
        cursor = item['id']
        try:
            row = ImportRow.model_validate(item['row']).model_dump(mode='json')
            if row['source'] != 'aleto':
                raise ValueError('Unexpected source')
        except (ValidationError, ValueError) as exc:
            source = item['row']
            entries.append({
                'id': cursor, 'status': 'rejected',
                'article': str(source.get('source_article', ''))[:150] if isinstance(source, dict) else '',
                'fields': [list(error['loc']) for error in exc.errors(include_input=False, include_context=False)]
                if isinstance(exc, ValidationError) else [['source']],
            })
        else:
            entries.append({'id': cursor, 'status': 'prepared', 'article': row['source_article'],
                            'upload_row': len(rows) + 1})
            rows.append(row)
    upload_id = None
    if rows:
        checksum = digest(rows)
        upload = CatalogueJob(actor_id=who.actor_id, filename=f'Aleto-worker-{job_id}-{data.cursor}.json',
                              file_sha256=checksum, payload_sha256=checksum, rows=rows, format='v2',
                              status='uploaded', resolutions={}, report={})
        db.add(upload)
        db.flush()
        upload_id = upload.id
    updated = {'cursor': cursor, 'seen': run['seen'] + len(items),
               'rejected': run['rejected'] + len(items) - len(rows), 'done': result['done']}
    db.execute(text("""
        INSERT INTO aleto_import_runs(actor_id, job_id, cursor, seen, rejected, done)
        VALUES (:actor, :job, :cursor, :seen, :rejected, :done)
        ON CONFLICT (actor_id, job_id) DO UPDATE SET cursor=excluded.cursor, seen=excluded.seen,
            rejected=excluded.rejected, done=excluded.done
    """), {**params, **updated})
    if entries:
        db.execute(text("""
            INSERT INTO aleto_import_batches(actor_id, job_id, start_cursor, end_cursor, catalogue_job_id, entries)
            VALUES (:actor, :job, :start, :end, :upload, CAST(:entries AS jsonb))
        """), {**params, 'start': data.cursor, 'end': cursor, 'upload': upload_id, 'entries': json.dumps(entries)})
    db.commit()
    return updated
