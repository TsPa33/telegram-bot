"""Staging-specific behavior against the dedicated local PostgreSQL test DB."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.config import database_url
from app.db import engine
from app.main import app
from app import staging


def test_staging_public_host_and_authenticated_sales_readiness():
    """Import the real app in staging mode, including its startup host allowlist."""
    import os
    import sys
    from subprocess import run

    origin = "https://confident-sparkle-warehouse-staging.up.railway.app"
    script = r'''
import os
from fastapi.testclient import TestClient
from app.main import app

origin = os.environ['WAREHOUSE_PUBLIC_ORIGIN']
path = '/api/v1/sales-workspace/readiness'
with TestClient(app, base_url=origin) as c:
    assert c.get(path, headers={'Host': 'untrusted.example.test'}).status_code == 400
    assert c.get(path).status_code == 401
    assert c.get('/health', headers={'Host': 'healthcheck.railway.app'}).status_code == 200
    c.headers['Origin'] = origin
    r = c.post('/api/v1/auth/register', json={
        'name': 'Host regression', 'email': 'host-regression@example.test',
        'password': 'local-host-test-password'})
    assert r.status_code == 201, r.text
    assert all('Secure' in cookie and 'SameSite=strict' in cookie and 'Domain=' not in cookie
               for cookie in r.headers.get_list('set-cookie'))
    c.headers['X-CSRF-Token'] = r.json()['csrf_token']
    assert c.post('/api/v1/auth/logout').status_code == 204
    credentials = {'email': 'host-regression@example.test', 'password': 'local-host-test-password'}
    assert c.post('/api/v1/auth/login', json=credentials,
                  headers={'Origin': 'https://telegram-bot-warehouse-staging.up.railway.app'}).status_code == 403
    r = c.post('/api/v1/auth/login', json=credentials)
    assert r.status_code == 200, r.text
    c.headers['X-CSRF-Token'] = r.json()['csrf_token']
    assert c.get('/api/v1/auth/me').status_code == 200
    # Direct backend ingress is allowed, without allowing its Origin for mutations.
    assert c.get(path, headers={'Host': 'telegram-bot-warehouse-staging.up.railway.app'}).status_code == 200
    r = c.get(path)
    assert r.status_code == 200, r.text
    assert r.json()['contract_version'] == 5
    assert r.json()['database_revisions'] == ['021e8f6f220c']
    assert c.get(path, headers={'Host': 'untrusted.example.test'}).status_code == 400
    assert c.post('/api/v1/auth/logout', headers={'Origin': 'https://untrusted.example.test'}).status_code == 403
    assert c.post('/api/v1/auth/logout', headers={'X-CSRF-Token': 'invalid'}).status_code == 403
    assert c.post('/api/v1/auth/logout').status_code == 204
    assert c.get(path).status_code == 401
'''
    result = run([sys.executable, '-c', script], env={
        **os.environ, 'WAREHOUSE_ENV': 'staging',
        'WAREHOUSE_COOKIE_SECURE': 'true', 'WAREHOUSE_PUBLIC_ORIGIN': origin,
        'WAREHOUSE_ALLOWED_HOSTS': 'telegram-bot-warehouse-staging.up.railway.app',
        'WAREHOUSE_REGISTRATION_ENABLED': 'true', 'PLAN_PARTS_ENABLED': 'false',
    }, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    mismatch = run([sys.executable, '-c', '''
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app, base_url="https://telegram-bot-warehouse-staging.up.railway.app") as c:
    r = c.get('/api/v1/sales-workspace/readiness')
    assert r.status_code == 400 and r.text == 'Invalid host header'
'''], env={**os.environ, 'WAREHOUSE_ENV': 'staging',
           'WAREHOUSE_COOKIE_SECURE': 'true',
           'WAREHOUSE_PUBLIC_ORIGIN': 'https://different.example.test',
           'WAREHOUSE_ALLOWED_HOSTS': ''},
        capture_output=True, text=True)
    assert mismatch.returncode == 0, mismatch.stdout + mismatch.stderr


def test_component_database_url_encodes_password(monkeypatch):
    with monkeypatch.context() as m:
        m.delenv("WAREHOUSE_DATABASE_URL")
        for key, value in {
            "HOST": "localhost",
            "PORT": "5432",
            "NAME": "warehouse_staging_test",
            "USER": "test_user",
            "PASSWORD": "test-only:/@password",
        }.items():
            m.setenv("WAREHOUSE_DB_" + key, value)
        database_url.cache_clear()
        url = make_url(database_url())
        assert url.password == "test-only:/@password"
        assert url.database == "warehouse_staging_test"
    database_url.cache_clear()


def test_staging_origin_cookies_and_registration(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_COOKIE_SECURE", "true")
    monkeypatch.setenv("WAREHOUSE_PUBLIC_ORIGIN", "https://testserver")
    with TestClient(app, base_url="https://testserver") as c:
        assert c.get("/api/v1/auth/options").json() == {"registration_enabled": False}
        data = {
            "name": "Staging fixture",
            "email": "staging@example.test",
            "password": "test-only-long-password",
        }
        assert c.post("/api/v1/auth/register", json=data).status_code == 403
        c.headers["Origin"] = "https://testserver"
        assert c.post("/api/v1/auth/register", json=data).status_code == 403
        monkeypatch.setenv("WAREHOUSE_REGISTRATION_ENABLED", "true")
        r = c.post("/api/v1/auth/register", json=data)
        assert r.status_code == 201
        cookies = r.headers.get_list("set-cookie")
        assert all("Secure" in h and "SameSite=strict" in h for h in cookies)
        assert "HttpOnly" in cookies[0] and "Path=/api/v1" in cookies[0]
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        assert c.get("/api/v1/auth/me").status_code == 200
        c.headers["Origin"] = "https://other.example.test"
        assert c.post("/api/v1/auth/logout").status_code == 403
        c.headers["Origin"] = "https://testserver"
        c.headers["X-CSRF-Token"] = "wrong-csrf"
        assert c.post("/api/v1/auth/logout").status_code == 403
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        assert c.post("/api/v1/auth/logout").status_code == 204


def test_health_requires_exact_migration_head(client):
    assert client.get("/health").status_code == 200
    with engine().begin() as conn:
        previous = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        conn.execute(
            text("UPDATE alembic_version SET version_num='outdated-test-head'")
        )
    try:
        assert client.get("/health").status_code == 503
    finally:
        with engine().begin() as conn:
            conn.execute(
                text("UPDATE alembic_version SET version_num=:version"),
                {"version": previous},
            )
    assert client.get("/health").status_code == 200


def test_staging_migrations_are_repeatable(vehicle):
    staging.migrate()
    staging.migrate()
    with engine().connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM vehicles WHERE id=:id"),
                {"id": vehicle["id"]},
            ).scalar_one()
            == 1
        )
        assert (
            frozenset(
                conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
            )
            == staging.migration_heads()
        )


def test_migration_lock_excludes_competing_startups():
    with engine().connect() as blocker:
        blocker.execute(
            text("SELECT pg_advisory_lock(:key)"), {"key": staging.MIGRATION_LOCK}
        )
        blocker.commit()
        try:
            with pytest.raises(RuntimeError, match="migration lock timeout"):
                staging.migrate(timeout=0.01)
        finally:
            blocker.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": staging.MIGRATION_LOCK}
            )
            blocker.commit()
    staging.migrate()


def test_failed_migration_rolls_back_and_releases_lock(monkeypatch):
    def broken_upgrade(config, target):
        config.attributes["connection"].execute(
            text("CREATE TABLE warehouse_failed_migration_probe(id integer)")
        )
        raise RuntimeError("simulated migration failure")

    with monkeypatch.context() as m:
        m.setattr(staging.command, "upgrade", broken_upgrade)
        with pytest.raises(RuntimeError, match="simulated migration failure"):
            staging.migrate()
    with engine().connect() as conn:
        assert (
            conn.execute(
                text("SELECT to_regclass('warehouse_failed_migration_probe')")
            ).scalar_one()
            is None
        )
        assert conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": staging.MIGRATION_LOCK}
        ).scalar_one()
        conn.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": staging.MIGRATION_LOCK}
        )
        conn.commit()
    staging.migrate()


def test_owner_bootstrap_no_seed_or_password_reset(monkeypatch):
    from app import create_owner

    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    answers = iter(["Test owner", "owner-fixture@example.test"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(
        create_owner.getpass, "getpass", lambda prompt: "test-owner-long-password"
    )
    create_owner.main()
    with engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM accounts")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM parts")).scalar_one() == 0
    answers = iter(["Test owner", "owner-fixture@example.test"])
    with pytest.raises(RuntimeError, match="already exists"):
        create_owner.main()


@pytest.mark.parametrize("invalid", ["*", "*.railway.app", "https://backend.example.test", "backend.example.test:8010", "backend.example.test/", "good.example.test,", "UPPER.example.test", "-bad.example.test"])
def test_allowed_hosts_rejects_unsafe_configuration(monkeypatch, invalid):
    from app.config import allowed_hosts
    monkeypatch.setenv("WAREHOUSE_PUBLIC_ORIGIN", "https://frontend.example.test")
    monkeypatch.setenv("WAREHOUSE_ALLOWED_HOSTS", invalid)
    with pytest.raises(RuntimeError, match="WAREHOUSE_ALLOWED_HOSTS"):
        allowed_hosts()


def test_allowed_hosts_preserves_frontend_and_healthcheck(monkeypatch):
    from app.config import allowed_hosts
    monkeypatch.setenv("WAREHOUSE_PUBLIC_ORIGIN", "https://frontend.example.test")
    monkeypatch.delenv("WAREHOUSE_ALLOWED_HOSTS", raising=False)
    assert allowed_hosts() == ["frontend.example.test", "healthcheck.railway.app"]
    monkeypatch.setenv("WAREHOUSE_ALLOWED_HOSTS", "backend.example.test, backend.example.test")
    assert allowed_hosts() == ["frontend.example.test", "healthcheck.railway.app", "backend.example.test"]
