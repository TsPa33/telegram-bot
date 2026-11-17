import os
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ADMIN_URL = os.environ.get("CONTROL_CENTER_TEST_ADMIN_URL", "")
if (
    not ADMIN_URL.startswith("postgresql+psycopg://")
    or "@127.0.0.1:" not in ADMIN_URL
    or not ADMIN_URL.endswith("_test")
):
    raise RuntimeError("Explicit local disposable *_test administrator URL required")
admin_engine = create_engine(ADMIN_URL)
os.environ.update(
    CONTROL_CENTER_ENABLED="true",
    CONTROL_CENTER_SOURCE_ENVIRONMENT="local",
    CONTROL_CENTER_ORIGIN="http://testserver",
    CONTROL_CENTER_MFA_KEY=Fernet.generate_key().decode(),
    CONTROL_CENTER_DATABASE_URL=ADMIN_URL.replace(
        "postgres:disposable-control-tests-only", "cc_app:cc-local-tests-only"
    ),
)
from app.control_center.config import connection
from app.control_center.models import Staff
from app.control_center.security import hasher
from app.control_center.config import cipher
from app.control_center.api import create_app
from test_support import SECRET


@pytest.fixture(autouse=True)
def schema():
    root = Path(__file__).resolve().parents[1]
    with admin_engine.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS control_center CASCADE"))
        c.connection.driver_connection.execute(
            (root / "control_center_migrations/001.sql").read_text()
        )
        c.execute(
            text("INSERT INTO control_center.schema_version VALUES ('001','local')")
        )
        c.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='cc_app') THEN CREATE ROLE cc_app LOGIN PASSWORD 'cc-local-tests-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; END $$"
            )
        )
        grants = (
            (root / "control_center_migrations/grants.sql")
            .read_text()
            .replace(':"app_role"', "cc_app")
            .replace(':"operator_role"', "cc_app")
        )
        c.connection.driver_connection.execute(grants)
    connection().dispose()
    yield


@pytest.fixture
def db():
    with Session(admin_engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def staff_factory(db):
    def make(role="Owner", username=None, finance=False):
        row = Staff(
            username=username or role.lower(),
            role=role,
            password_hash=hasher.hash("long-staff-test-password"),
            mfa_ciphertext=cipher().encrypt(SECRET.encode()).decode(),
            finance=finance,
            active=True,
            last_totp_step=-1,
        )
        db.add(row)
        db.commit()
        return row

    return make


@pytest.fixture
def client():
    parent = FastAPI()
    parent.mount("/api/control", create_app())
    with TestClient(
        parent, base_url="http://testserver", headers={"Origin": "http://testserver"}
    ) as c:
        yield c
