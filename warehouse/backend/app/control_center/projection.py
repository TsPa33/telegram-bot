"""Explicit bounded snapshot reconciler. No customer identity or write-capable API.

A sweep uses (created_at,id) keysets and repeats from the start on completion.
Every source transaction is REPEATABLE READ READ ONLY. Existing records are
refreshed again each sweep; no updated_at timestamp assumptions, no lost ties.
"""

from datetime import datetime, timedelta
from sqlalchemy import func, select, text, tuple_, update
from sqlalchemy.orm import Session, load_only
from .config import connection, environment
from .models import Company, SourceLink, SourceState, now


def json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def upsert(db, record, env):
    company = db.scalar(
        select(Company)
        .where(
            Company.environment == env, Company.workspace_id == record["workspace_id"]
        )
        .with_for_update()
    )
    if company is None:
        company = Company(
            environment=env,
            workspace_id=record["workspace_id"],
            display_name=record["display_name"],
            registered_at=record["registered_at"],
            search_text="",
            snapshot={},
            fetched_at=now(),
        )
        db.add(company)
        db.flush()
    company.display_name = record["display_name"]
    company.snapshot = json_safe(record["snapshot"])
    company.search_text = (record["display_name"] + " " + record["owner_email"]).lower()
    company.fetched_at = now()
    link = db.scalar(
        select(SourceLink).where(
            SourceLink.company_id == company.id, SourceLink.system == "warehouse"
        )
    )
    if not link:
        db.add(
            SourceLink(
                company_id=company.id,
                system="warehouse",
                environment=env,
                entity_type="workspace",
                source_id=company.workspace_id,
                status="verified",
                evidence="warehouse:director-owner",
                verified_by="warehouse-read-adapter",
                verified_at=now(),
            )
        )
    # Only the existing local canonical projection is evidence. Never mint binding.
    binding = record["snapshot"].get("binding")
    old = db.scalar(
        select(SourceLink).where(
            SourceLink.company_id == company.id, SourceLink.system == "billing"
        )
    )
    if binding:
        expected_environment = "production" if env == "production" else "sandbox"
        mismatch = binding["environment"] != expected_environment
        if old and (
            mismatch
            or old.source_id != binding["id"]
            or old.environment != binding["environment"]
        ):
            old.status = "conflict"
        elif not old:
            db.add(
                SourceLink(
                    company_id=company.id,
                    system="billing",
                    environment=binding["environment"],
                    entity_type="binding",
                    source_id=binding["id"],
                    status="conflict" if mismatch else "verified",
                    evidence="warehouse-entitlement:" + company.workspace_id,
                    verified_by="warehouse-read-adapter",
                    verified_at=now(),
                )
            )
    elif old:
        old.status = "revoked"
    return company


from app.services.control_directory import continuous_paid_end, read_batch as source_read_batch

def read_batch(source, cursor, limit):
    return source_read_batch(source, cursor, limit, environment())


def sync_batch(db, limit=50):
    if not 1 <= limit <= 100:
        raise ValueError("Batch size must be 1..100")
    env = environment()
    # Serialize concurrent operator syncs; lock released with each bounded commit.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('control-center-sync'))"))
    key = "warehouse:" + env
    state = db.get(SourceState, key)
    if not state:
        state = SourceState(
            key=key, environment=env, schema_version="1", coverage="incomplete"
        )
        db.add(state)
        db.flush()
    try:
        import os
        if os.getenv("CONTROL_CENTER_WAREHOUSE_SOURCE_URL"):
            from .source_client import fetch_batch
            records, cursor = fetch_batch(state.watermark, limit)
        else:
            with Session(connection("CONTROL_CENTER_WAREHOUSE_READ_URL")) as source:
                source.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
                records, cursor = read_batch(source, state.watermark, limit)
        # Archive synthetic data only after a successful real-source response.
        if env == "staging" and state.schema_version == "001" and os.getenv("CONTROL_CENTER_PREVIEW") == "true" and os.getenv("CONTROL_CENTER_WAREHOUSE_SOURCE_URL"):
            demo_ids = select(SourceLink.company_id).where(SourceLink.environment == "staging", SourceLink.system == "warehouse", SourceLink.evidence == "synthetic-preview")
            db.execute(update(Company).where(Company.id.in_(demo_ids)).values(environment="preview"))
            db.execute(update(SourceLink).where(SourceLink.company_id.in_(select(Company.id).where(Company.environment == "preview"))).values(environment="preview"))
        for record in records:
            upsert(db, record, env)
        from app.staging import migration_heads

        state.schema_version = "1/" + ",".join(sorted(migration_heads()))
        state.watermark, state.fetched_at, state.last_success = cursor, now(), now()
        state.last_error = None
        state.coverage = "sweep_complete" if cursor is None else "partial_sweep"
        db.commit()
        return dict(processed=len(records), next_cursor=cursor, coverage=state.coverage)
    except Exception:
        # Do not preserve partial rows or move the watermark past a failed batch.
        db.rollback()
        state = db.get(SourceState, key)
        if not state:
            state = SourceState(
                key=key, environment=env, schema_version="1", coverage="incomplete"
            )
            db.add(state)
        state.last_error = "source_read_failed"  # never exception strings/DSN
        db.commit()
        raise RuntimeError("Warehouse read synchronization failed") from None
