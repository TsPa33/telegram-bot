"""Staging-specific behavior against the dedicated local PostgreSQL test DB."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.config import database_url
from app.db import engine
from app.main import app
from app import staging


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
