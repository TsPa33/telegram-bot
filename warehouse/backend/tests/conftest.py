import os
import sys
from subprocess import run
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

url = os.environ.get("WAREHOUSE_TEST_DATABASE_URL", "")
if not url or not url.rsplit("/", 1)[-1].endswith("_test"):
    raise RuntimeError(
        "Set WAREHOUSE_TEST_DATABASE_URL to a dedicated warehouse*_test PostgreSQL database; tests erase it"
    )
os.environ["WAREHOUSE_DATABASE_URL"] = url
os.environ["WAREHOUSE_COOKIE_SECURE"] = "false"
from app.main import app
from app.db import engine
from app.services.auth import _attempts


@pytest.fixture(scope="session", autouse=True)
def migrated():
    run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)


@pytest.fixture(autouse=True)
def clean(migrated):
    with engine().begin() as conn:
        conn.execute(
            text(
                "TRUNCATE photos, operations, parts, categories, vehicles, sessions, accounts CASCADE"
            )
        )
    with engine().begin() as conn:
        conn.execute(text('TRUNCATE catalogue_sources, catalogue_entities, catalogue_state CASCADE'))
        conn.execute(text('INSERT INTO catalogue_state (id,revision) VALUES (1,0)'))
    _attempts.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def signup(c, email="owner@example.test"):
    r = c.post(
        "/api/v1/auth/register",
        json={"name": "Власник", "email": email, "password": "a-long-test-password"},
    )
    assert r.status_code == 201, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r.json()["user"]


@pytest.fixture
def logged(client):
    signup(client)
    return client


@pytest.fixture
def vehicle_data():
    return {
        "manufacturer": "Test manufacturer",
        "model": "Test model",
        "year": 2020,
        "donor_id": "TEST-1",
        "acquisition_date": "2026-01-01",
        "acquisition_cost": "100.00",
    }


@pytest.fixture
def vehicle(logged, vehicle_data):
    r = logged.post("/api/v1/vehicles", json=vehicle_data)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def part(logged, vehicle):
    r = logged.post(
        "/api/v1/parts",
        json={
            "name": "Test part",
            "vehicle_id": vehicle["id"],
            "selling_price": "50.00",
            "unit_cost": "20.00",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def catalog():
    return {
        "source": "test-only-fixture",
        "nodes": [
            {"key": "a", "name": "Group A", "kind": "category"},
            {"key": "b", "name": "Group B", "kind": "category"},
            {
                "key": "a-1",
                "parent_key": "a",
                "name": "Same name",
                "kind": "subcategory",
            },
            {
                "key": "b-1",
                "parent_key": "b",
                "name": "Same name",
                "kind": "subcategory",
            },
            {
                "key": "part",
                "parent_key": "a-1",
                "name": "Test checklist part",
                "kind": "part",
            },
        ],
    }
