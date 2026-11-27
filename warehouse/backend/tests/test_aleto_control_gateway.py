import csv
import io
import json

from fastapi.testclient import TestClient

from app import aleto_control as control
from app.aleto_results import process_export
from app.aleto_worker import database, select_catalogue
from app.api import aleto_control
from app.services.aleto_adapter import fixture, run_fixture
from test_catalogue_v2 import counts, platform  # noqa: F401


def test_large_import_resumes_and_full_export_is_filtered(platform, monkeypatch, tmp_path):
    path = tmp_path / 'aleto.sqlite3'
    monkeypatch.setenv('CARPOT_ALETO_DATABASE', str(path))
    monkeypatch.setenv('CARPOT_ALETO_TOKEN', 'a' * 40)
    _, raw = run_fixture('XC60', fixture('XC60')[1], lambda *_: None)
    template = {**json.loads(raw)['rows'][0], 'source': 'aleto'}
    oracle = TestClient(control.app)
    owner = platform.get('/api/v1/auth/me').json()['id']
    headers = {'Authorization': 'Bearer ' + 'a' * 40, 'X-Workspace': owner, 'X-Actor': owner}
    job_id = oracle.post('/jobs', headers=headers, json={'manufacturer': 'BMW', 'model': 'X4'}).json()['id']
    # A completed catalogue with 20,037 observations and one intentionally malformed row.
    size = 20037
    with database(path) as db:
        url = 'https://aleto.ua/car/bmw-x4/'
        select_catalogue(db, job_id, url)
        db.executemany('INSERT INTO market_observations VALUES (?, ?, ?, ?)', (
            (job_id, url, str(i), json.dumps({
                **template, 'source_article': f'A-{i:05d}', 'part_name': '=Фара' if i % 2 else 'Бампер',
                'price_uah': str(i), 'manufacturer': '' if i == 731 else 'BMW',
            })) for i in range(1, size + 1)
        ))
        db.execute("UPDATE parser_jobs SET status='completed' WHERE id=?", (job_id,))
    db.close()

    from fastapi import HTTPException
    import httpx

    seen_paths = []

    def worker(who, method, route, payload=None):
        assert who.workspace_account_id == who.actor_id == owner
        seen_paths.append(route)
        response = oracle.request(method, route, headers=headers, json=payload)
        if response.status_code >= 400:
            raise HTTPException(response.status_code)
        return response.json()

    monkeypatch.setattr(aleto_control, 'worker', worker)
    base = f'/api/v1/admin/aleto-worker/jobs/{job_id}'
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_NAME', raising=False)
    assert platform.post(base + '/prepare', json={'cursor': 0}).status_code == 403
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_NAME', 'warehouse-staging')
    before = counts()
    first = platform.post(base + '/prepare', json={'cursor': 0}).json()
    assert first == {'cursor': 500, 'seen': 500, 'rejected': 0, 'done': False}
    assert platform.post(base + '/prepare', json={'cursor': 0}).json() == first
    assert len(seen_paths) == 1
    run = platform.get(base + '/prepare').json()
    while not run['done']:
        response = platform.post(base + '/prepare', json={'cursor': run['cursor']})
        assert response.status_code == 200, response.text
        run = response.json()
    assert run == {'cursor': size, 'seen': size, 'rejected': 1, 'done': True}
    assert platform.post(base + '/prepare', json={'cursor': run['cursor']}).json() == run
    batches, offset = [], 0
    while offset is not None:
        page = platform.get(base + '/prepare', params={'offset': offset}).json()
        batches.extend(page['batches'])
        offset = page['next_offset']
    assert len(batches) == 41
    assert [row['id'] for batch in batches for row in batch['entries']] == list(range(1, size + 1))
    assert [row['id'] for batch in batches for row in batch['entries'] if row['status'] == 'rejected'] == [731]
    assert len({batch['catalogue_job_id'] for batch in batches}) == 41
    assert counts() == before

    query = {'q': 'ФАРА', 'sort': 'price_uah', 'direction': 'desc'}
    page = platform.get(base + '/results', params=query).json()
    assert len(page['items']) == 50 and page['next_offset'] == 50
    assert page['items'][0]['source_article'] == 'A-20037'
    export = platform.post(base + '/exports', json=query).json()['id']
    full = platform.post(base + '/exports', json={}).json()['id']
    db = database(path)
    with db:
        assert process_export(db, path)
    db.close()
    # Reopen the store between asynchronous requests.
    db = database(path)
    with db:
        assert process_export(db, path)
    db.close()
    assert platform.get(base + '/exports/' + export).json()['row_count'] == 10019
    assert platform.get(base + '/exports/' + full).json()['row_count'] == size

    # Use the real Warehouse streaming gateway with an in-process Oracle transport.
    upstream_client = httpx.Client

    def adapter(*_, **kwargs):
        def relay(request):
            local = oracle.request(request.method, request.url.path, headers=headers)
            return httpx.Response(local.status_code, content=local.content)
        return upstream_client(transport=httpx.MockTransport(relay), **kwargs)

    monkeypatch.setattr(aleto_control, 'worker_request', lambda who, route: ('https://worker.test' + route, headers))
    monkeypatch.setattr(aleto_control.httpx, 'Client', adapter)
    download = platform.get(base + '/exports/' + export + '/download')
    assert download.status_code == 200
    lines = list(csv.DictReader(io.StringIO(download.content.decode('utf-8-sig'))))
    assert len(lines) == 10019 and lines[0]['part_name'] == "'=Фара"
    assert lines[0]['source_article'] == 'A-20037' and lines[-1]['source_article'] == 'A-00001'
    download = platform.get(base + '/exports/' + full + '/download')
    assert sum(1 for _ in csv.DictReader(io.StringIO(download.content.decode('utf-8-sig')))) == size
    assert oracle.get(f'/jobs/{job_id}/exports/{export}', headers={**headers, 'X-Workspace': 'another'}).status_code == 404


def test_aleto_worker_private_http_is_restricted_to_railway_staging(monkeypatch):
    from types import SimpleNamespace

    import pytest
    from fastapi import HTTPException

    actor = SimpleNamespace(workspace_account_id='workspace-1', actor_id='actor-1')
    monkeypatch.setenv('WAREHOUSE_ALETO_WORKER_TOKEN', 't' * 40)
    monkeypatch.setenv('WAREHOUSE_ALETO_WORKER_PROXY',
                       'http://carpot-aleto-tailnet-proxy.railway.internal:1056')
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_NAME', 'warehouse-staging')
    monkeypatch.setenv('WAREHOUSE_ALETO_WORKER_URL',
                       'http://carpot-oracle.tailf95906.ts.net:8444')
    url, headers = aleto_control.worker_request(actor, '/jobs')
    assert url == 'http://carpot-oracle.tailf95906.ts.net:8444/jobs'
    assert headers['Authorization'] == 'Bearer ' + 't' * 40

    for bad_url in ('http://carpot-oracle.tailf95906.ts.net:8081',
                    'http://other.tailf95906.ts.net:8444',
                    'http://carpot-oracle.tailf95906.ts.net:8444/unexpected'):
        monkeypatch.setenv('WAREHOUSE_ALETO_WORKER_URL', bad_url)
        with pytest.raises(HTTPException) as exc:
            aleto_control.worker_request(actor, '/jobs')
        assert exc.value.status_code == 503

    monkeypatch.setenv('WAREHOUSE_ALETO_WORKER_URL',
                       'http://carpot-oracle.tailf95906.ts.net:8444')
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_NAME', 'production')
    with pytest.raises(HTTPException) as exc:
        aleto_control.worker_request(actor, '/jobs')
    assert exc.value.status_code == 503

    monkeypatch.setenv('RAILWAY_ENVIRONMENT_NAME', 'warehouse-staging')
    monkeypatch.delenv('WAREHOUSE_ALETO_WORKER_PROXY')
    with pytest.raises(HTTPException) as exc:
        aleto_control.worker_request(actor, '/jobs')
    assert exc.value.status_code == 503
