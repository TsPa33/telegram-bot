"""Local-only real API/PG browser fixture. Never part of operational image."""

import os
from pathlib import Path
import json
import secrets
from datetime import timedelta
import psycopg
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import FastAPI
import uvicorn

url = os.environ["CONTROL_CENTER_BROWSER_ADMIN_URL"]
if "@127.0.0.1:" not in url or not url.endswith("_test"):
    raise RuntimeError("Browser fixtures require an explicit loopback *_test DB")
key = Fernet.generate_key().decode()
os.environ.update(
    CONTROL_CENTER_ENABLED="true",
    CONTROL_CENTER_SOURCE_ENVIRONMENT="local",
    CONTROL_CENTER_ORIGIN="http://127.0.0.1:5269",
    CONTROL_CENTER_MFA_KEY=key,
    CONTROL_CENTER_DATABASE_URL=url.replace(
        "postgres:disposable-control-tests-only", "cc_app:cc-local-tests-only"
    ),
)
from app.control_center.models import Staff, SourceState, now
from app.control_center.projection import upsert
from app.control_center.security import hasher
from app.control_center.api import create_app

root = Path(__file__).resolve().parents[1]
engine = create_engine(url)
with engine.begin() as c:
    c.execute(
        text(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='cc_app') THEN CREATE ROLE cc_app LOGIN PASSWORD 'cc-local-tests-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; END $$"
        )
    )
    c.execute(text("DROP SCHEMA IF EXISTS control_center CASCADE"))
    c.connection.driver_connection.execute(
        (root / "control_center_migrations/001.sql").read_text()
    )
    c.execute(text("INSERT INTO control_center.schema_version VALUES ('001','local')"))
    c.connection.driver_connection.execute(
        (root / "control_center_migrations/grants.sql")
        .read_text()
        .replace(':"app_role"', "cc_app")
        .replace(':"operator_role"', "cc_app")
    )
password = secrets.token_urlsafe(24)
seed = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
with Session(engine) as db:
    hashed = hasher.hash(password)
    for index in range(40):
        db.add(
            Staff(
                username="browser-" + str(index),
                role="Owner",
                password_hash=hashed,
                mfa_ciphertext=Fernet(key.encode()).encrypt(seed.encode()).decode(),
                active=True,
                finance=False,
                last_totp_step=-1,
            )
        )
    for index, name in enumerate(["Тестова компанія Альфа", "Тестова компанія Бета"]):
        upsert(
            db,
            dict(
                workspace_id="browser-workspace-" + str(index),
                display_name=name,
                owner_email="owner@example.test",
                registered_at=now(),
                snapshot=dict(
                    people=[
                        dict(
                            id="owner",
                            name="Тестовий власник",
                            email="owner@example.test",
                            role="DIRECTOR",
                            active=True,
                            last_login_at=now().isoformat(),
                        )
                    ],
                    access=dict(
                        status="ACTIVE",
                        plan="standard",
                        vehicle_capacity=10,
                        employee_seats=5,
                        period_end=(now() + timedelta(days=10)).isoformat(),
                        continuous_paid_until=(now() + timedelta(days=10)).isoformat(),
                    ),
                    usage=dict(vehicles=3, employees=1),
                    access_incomplete=False,
                    binding=None,
                    business_activity_at=now().isoformat(),
                    business_activity_coverage="synthetic disposable fixture",
                ),
            ),
            "local",
        )
    db.add(
        SourceState(
            key="warehouse:local",
            environment="local",
            schema_version="1",
            last_success=now(),
            fetched_at=now(),
            coverage="sweep_complete",
        )
    )
    db.commit()
fixture = Path(
    os.environ.get(
        "CONTROL_CENTER_BROWSER_FIXTURE_FILE", "/tmp/control-browser-fixture.json"
    )
)
fixture.write_text(json.dumps(dict(password=password, seed=seed)))
fixture.chmod(0o600)
parent = FastAPI()
parent.mount("/api/control", create_app())
uvicorn.run(parent, host="127.0.0.1", port=8029, log_level="warning", access_log=False)
