from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from app.control_center.models import Company, SourceLink, SourceState, now
from app.control_center.projection import continuous_paid_end, upsert, sync_batch
from app.control_center.config import connection
from test_support import authenticate


def record(workspace, name="Same"):
    return dict(
        workspace_id=workspace,
        display_name=name,
        registered_at=now(),
        owner_email="same@example.test",
        snapshot=dict(
            people=[],
            access={"status": "UNKNOWN"},
            binding=None,
            access_incomplete=True,
        ),
    )


def test_replay_dedup_preserves_notes_identity_no_email_merge(db):
    a = record("a")
    b = record("b")
    first = upsert(db, a, "local")
    db.commit()
    identity = first.id
    upsert(db, a, "local")
    upsert(db, b, "local")
    db.commit()
    assert db.scalar(select(func.count()).select_from(Company)) == 2
    assert db.scalar(select(Company).where(Company.workspace_id == "a")).id == identity
    assert db.scalar(select(func.count()).select_from(SourceLink)) == 2


def test_binding_conflict_not_auto_merged(db):
    r = record("a")
    r["snapshot"]["binding"] = {
        "id": "first",
        "account_id": "account-a",
        "environment": "sandbox",
    }
    c = upsert(db, r, "local")
    db.commit()
    r["snapshot"]["binding"] = {
        "id": "second",
        "account_id": "account-b",
        "environment": "production",
    }
    upsert(db, r, "local")
    db.commit()
    link = db.scalar(select(SourceLink).where(SourceLink.system == "billing"))
    assert link.status == "conflict" and link.source_id == "first"
    assert db.scalar(select(func.count()).select_from(Company)) == 1


def test_repeat_sweep_tied_timestamp_and_failure_watermark(db, monkeypatch):
    from app.control_center import projection
    from contextlib import contextmanager

    class Reader:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, *args):
            pass

    monkeypatch.setattr(projection, "Session", lambda _: Reader())
    monkeypatch.setattr(projection, "connection", lambda _: None)
    rows = [record("a"), record("b")]

    def batch(source, cursor, limit):
        return ([rows[0]], "same|a") if cursor is None else ([rows[1]], None)

    monkeypatch.setattr(projection, "read_batch", batch)
    sync_batch(db, 1)
    assert db.get(SourceState, "warehouse:local").watermark == "same|a"

    def broken(*a):
        raise RuntimeError("secret DSN must not persist")

    monkeypatch.setattr(projection, "read_batch", broken)
    import pytest

    with pytest.raises(RuntimeError, match="synchronization failed"):
        sync_batch(db, 1)
    s = db.get(SourceState, "warehouse:local")
    assert s.watermark == "same|a" and s.last_error == "source_read_failed"
    monkeypatch.setattr(projection, "read_batch", batch)
    sync_batch(db, 1)
    sync_batch(db, 1)
    sync_batch(db, 1)
    assert db.scalar(select(func.count()).select_from(Company)) == 2
    assert db.get(SourceState, "warehouse:local").watermark is None


def test_continuous_paid_periods_exclude_trial_and_gaps():
    at = datetime(2026, 11, 15, tzinfo=timezone.utc)

    def interval(start, end, kind="base"):
        return dict(
            kind=kind, effective_from=start.isoformat(), effective_until=end.isoformat()
        )

    periods = [
        interval(at - timedelta(days=1), at + timedelta(days=1)),
        interval(at + timedelta(days=1), at + timedelta(days=31)),
        interval(at + timedelta(days=32), at + timedelta(days=62)),
        interval(at, at + timedelta(days=365), "trial"),
    ]
    assert continuous_paid_end(periods, at) == (at + timedelta(days=31)).isoformat()
    assert continuous_paid_end([periods[-1]], at) is None


def test_stale_not_zero(client, staff_factory, db):
    r = record("a")
    upsert(db, r, "local")
    db.add(
        SourceState(
            key="warehouse:local",
            environment="local",
            schema_version="1",
            last_success=now() - timedelta(hours=1),
            last_error="source_read_failed",
            coverage="partial_sweep",
        )
    )
    db.commit()
    authenticate(client, staff_factory())
    data = client.get("/api/control/overview").json()
    assert data["source"]["state"] == "stale" and data["workspaces"] == 1
    assert data["metrics"]["cash_collected"]["state"] == "unavailable"


def test_production_workspace_cannot_adopt_sandbox_binding(db):
    r = record("production-workspace")
    r["snapshot"]["binding"] = {
        "id": "sandbox-binding",
        "account_id": "sandbox-account",
        "environment": "sandbox",
    }
    upsert(db, r, "production")
    db.commit()
    link = db.scalar(select(SourceLink).where(SourceLink.system == "billing"))
    assert link.status == "conflict"


def test_real_sync_requires_rotation_and_archives_only_demo(db, monkeypatch):
    from app.control_center import projection, sync_worker
    from app.control_center.models import Audit, Staff
    from app.control_center.security import audit
    from sqlalchemy.orm import Session
    from app.control_center import source_client
    import pytest

    monkeypatch.setenv("CONTROL_CENTER_SOURCE_ENVIRONMENT", "staging")
    monkeypatch.setenv("CONTROL_CENTER_PREVIEW", "true")
    monkeypatch.setenv(
        "CONTROL_CENTER_WAREHOUSE_SOURCE_URL", "https://source.example.test"
    )
    demo = upsert(db, record("demo", "Demo"), "staging")
    link = db.scalar(select(SourceLink).where(SourceLink.company_id == demo.id))
    link.evidence = "synthetic-preview"
    db.add(
        SourceState(
            key="warehouse:staging",
            environment="staging",
            schema_version="001",
            coverage="sweep_complete",
            last_success=now(),
        )
    )
    db.commit()
    real = record("real", "Real")
    real["snapshot"]["source_environment"] = "staging"
    monkeypatch.setattr(source_client, "fetch_batch", lambda *a: ([real], None))
    monkeypatch.setattr(sync_worker, "connection", lambda: db.bind)
    assert sync_worker.refresh_once() == 15
    db.expire_all()
    assert db.get(Company, demo.id).environment == "staging"
    owner = Staff(
        username="owner-preview",
        role="Owner",
        password_hash="test",
        mfa_ciphertext="test",
        active=True,
    )
    db.add(owner)
    db.flush()
    audit(db, owner.id, "auth.rotate", "staff", owner.id)
    db.commit()
    assert sync_worker.refresh_once() == 300
    db.expire_all()
    assert db.get(Company, demo.id).environment == "preview"
    assert (
        db.scalar(
            select(func.count())
            .select_from(Company)
            .where(Company.environment == "staging")
        )
        == 1
    )
    assert db.get(SourceState, "warehouse:staging").schema_version.startswith("1/")
    assert (
        db.scalar(
            select(SourceLink).where(SourceLink.company_id == demo.id)
        ).environment
        == "preview"
    )


def test_denied_rotation_audit_does_not_enable_source_refresh(db, monkeypatch):
    from app.control_center import sync_worker
    from app.control_center.models import Staff, Audit

    monkeypatch.setenv("CONTROL_CENTER_SOURCE_ENVIRONMENT", "staging")
    monkeypatch.setenv("CONTROL_CENTER_PREVIEW", "true")
    monkeypatch.setenv(
        "CONTROL_CENTER_WAREHOUSE_SOURCE_URL", "https://source.example.test"
    )
    monkeypatch.setattr(sync_worker, "connection", lambda: db.bind)
    owner = Staff(
        username="denied-owner",
        role="Owner",
        active=True,
        password_hash="test",
        mfa_ciphertext="test",
    )
    db.add(owner)
    db.flush()
    db.add(
        Audit(
            actor=owner.id,
            permission="auth.rotate",
            scope="staff",
            target=owner.id,
            request_id="denied",
            safe_diff={},
            result="denied",
        )
    )
    db.commit()

    def unexpected(*args):
        raise AssertionError("Denied MFA attempt must not unlock source sync")

    monkeypatch.setattr(sync_worker, "sync_batch", unexpected)
    assert sync_worker.refresh_once() == 15
