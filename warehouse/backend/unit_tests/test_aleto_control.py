from contextlib import closing

from fastapi.testclient import TestClient

from app.aleto_control import app, connection


def test_worker_commands_are_scoped_and_audited(tmp_path, monkeypatch):
    monkeypatch.setenv('CARPOT_ALETO_DATABASE', str(tmp_path / 'control.sqlite3'))
    token = 'a' * 40
    monkeypatch.setenv('CARPOT_ALETO_TOKEN', token)
    headers = {'Authorization': 'Bearer ' + token, 'X-Workspace': 'first', 'X-Actor': 'owner'}
    client = TestClient(app)
    assert client.get('/jobs').status_code == 401
    response = client.post('/jobs', headers=headers, json={'manufacturer': 'BMW', 'model': 'X4', 'year': 2020})
    assert response.status_code == 200
    created = response.json()
    command = f"/jobs/{created['id']}/command"
    other = {**headers, 'X-Workspace': 'second'}
    assert client.get('/jobs', headers=other).json() == {'items': []}
    assert client.post(command, headers=other, json={'action': 'pause'}).status_code == 404
    assert client.post(command, headers=headers, json={'action': 'pause'}).json()['status'] == 'paused'
    assert client.post(command, headers=headers, json={'action': 'resume'}).json()['status'] == 'queued'
    assert client.post(command, headers=headers, json={'action': 'choose', 'url': 'https://example.org'}).status_code == 409
    with closing(connection()) as db:
        assert [tuple(row) for row in db.execute(
            'SELECT actor, action FROM parser_audit ORDER BY id',
        )] == [('owner', 'create'), ('owner', 'pause'), ('owner', 'resume')]


def test_registered_gateway_permissions():
    from app.permissions import route_permissions

    base = '/api/v1/admin/aleto-worker/jobs'
    assert route_permissions('GET', base, {}) == ['catalog_parser_view']
    assert route_permissions('POST', base, {}) == ['catalog_parser_view', 'catalog_parser_manage']
    assert route_permissions('POST', base + '/{job_id}/command', {'action': 'schedule'}) == [
        'catalog_parser_view', 'catalog_parser_admin',
    ]
    assert route_permissions('POST', base + '/{job_id}/prepare', {}) == [
        'catalog_parser_view', 'catalog_parser_publish',
    ]


def test_due_schedule_reuses_queue_and_enqueues_once(tmp_path, monkeypatch):
    from app.aleto_control import enqueue_due
    from app.aleto_worker import select_catalogue

    monkeypatch.setenv('CARPOT_ALETO_DATABASE', str(tmp_path / 'scheduler.sqlite3'))
    monkeypatch.setenv('CARPOT_ALETO_TOKEN', 'b' * 40)
    headers = {'Authorization': 'Bearer ' + 'b' * 40, 'X-Workspace': 'first', 'X-Actor': 'owner'}
    client = TestClient(app)
    job_id = client.post('/jobs', headers=headers, json={'manufacturer': 'Audi', 'model': 'Q5'}).json()['id']
    url = 'https://aleto.ua/car/audi-q5-18-/'
    with closing(connection()) as db, db:
        select_catalogue(db, job_id, url)
        db.execute("UPDATE parser_jobs SET status='completed' WHERE id=?", (job_id,))
    schedule = client.post(f'/jobs/{job_id}/command', headers=headers, json={'action': 'schedule'})
    assert schedule.json()['scheduled'] is True
    with closing(connection()) as db, db:
        db.execute('UPDATE parser_refresh SET due_at=0')
    enqueue_due()
    enqueue_due()
    jobs = client.get('/jobs', headers=headers).json()['items']
    assert [job['status'] for job in jobs] == ['queued', 'completed']
    assert jobs[0]['pages'] == {'queued': 1}
