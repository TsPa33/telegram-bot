"""Actual Warehouse migration + restricted source role; local disposable DB only."""

import os
from pathlib import Path
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from app.control_center.config import connection
from app.control_center.models import Company
from app.control_center.projection import read_batch, sync_batch
from app.models import Account
from test_support import authenticate


def test_actual_source_adapter_counts_workspaces_not_staff_and_is_read_only(
    db, client, staff_factory, monkeypatch
):
    # Explicit opt-in: fail if prerequisite is absent; never use live WAREHOUSE_DATABASE_URL.
    url = os.environ["CONTROL_CENTER_TEST_SOURCE_URL"]
    assert "@127.0.0.1:" in url and url.endswith("_test")
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("TRUNCATE accounts CASCADE"))
        c.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='cc_source') THEN CREATE ROLE cc_source LOGIN PASSWORD 'cc-source-tests-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; END $$"
            )
        )
        c.connection.driver_connection.execute(
            (
                Path(__file__).resolve().parents[1]
                / "control_center_migrations/source-grants.sql"
            )
            .read_text()
            .replace(':"reader_role"', "cc_source")
        )
    with Session(engine) as source:
        owner = Account(
            name="Owner Company",
            email="owner@source.test",
            password_hash="must-not-read",
            role="DIRECTOR",
        )
        source.add(owner)
        source.flush()
        worker = Account(
            name="Employee",
            email="employee@source.test",
            password_hash="must-not-read",
            role="MANAGER",
            workspace_account_id=owner.id,
        )
        source.add(worker)
        source.commit()
    monkeypatch.setenv(
        "CONTROL_CENTER_WAREHOUSE_READ_URL",
        url.replace(
            "postgres:disposable-control-tests-only", "cc_source:cc-source-tests-only"
        ),
    )
    source_engine = connection("CONTROL_CENTER_WAREHOUSE_READ_URL")
    with Session(source_engine) as source:
        source.execute(text("SET TRANSACTION READ ONLY"))
        records, cursor = read_batch(source, None, 10)
        assert len(records) == 1 and len(records[0]["snapshot"]["people"]) == 2
        assert records[0]["snapshot"]["usage"]["employees"] == 1
        assert "password_hash" not in str(records)
        assert records[0]["snapshot"]["access_incomplete"] is True
    # The deployed service adapter reuses the same actual read model and has
    # independent machine authorization rather than a customer session.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import control_directory as directory
    from app.services.control_transport import signature
    import time
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_CONTROL_DIRECTORY_ENABLED", "true")
    key="local-test-directory-key-"*3
    monkeypatch.setenv("WAREHOUSE_CONTROL_DIRECTORY_KEY",key)
    monkeypatch.setattr(directory,"engine",lambda:engine)
    source_app=FastAPI()
    source_app.include_router(directory.router)
    with TestClient(source_app) as c:
        stamp=str(int(time.time()))
        headers={"X-Control-Stamp":stamp,"X-Control-Signature":signature(key,stamp,"",20)}
        result=c.get("/internal/control/warehouse-directory",headers=headers)
        assert result.status_code==200,result.text
        assert result.json()["records"][0]["workspace_id"]==owner.id
        assert result.json()["records"][0]["snapshot"]["source_environment"]=="staging"
        assert "password_hash" not in result.text
        assert c.get("/internal/control/warehouse-directory").status_code==401
    import pytest
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        with source_engine.begin() as c:
            c.execute(text("UPDATE accounts SET name='tamper'"))
    with pytest.raises(DBAPIError):
        with source_engine.begin() as c:
            c.execute(text("SELECT password_hash FROM accounts"))
    assert sync_batch(db)["processed"] == 1
    assert sync_batch(db)["processed"] == 1
    assert db.scalar(select(func.count()).select_from(Company)) == 1
    authenticate(client, staff_factory())
    overview = client.get("/api/control/overview").json()
    assert overview["workspaces"] == 1 and overview["linked"] == 0
    engine.dispose()


def test_source_rejects_owner_credentials(monkeypatch):
    import pytest
    from app.control_center.config import connection

    connection.cache_clear()
    monkeypatch.setenv(
        "CONTROL_CENTER_WAREHOUSE_READ_URL",
        os.environ["CONTROL_CENTER_TEST_SOURCE_URL"],
    )
    with pytest.raises(RuntimeError, match="unprivileged"):
        with connection("CONTROL_CENTER_WAREHOUSE_READ_URL").connect():
            pass
    connection.cache_clear()
