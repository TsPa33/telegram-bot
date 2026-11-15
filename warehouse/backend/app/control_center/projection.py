"""Explicit bounded snapshot reconciler. No customer identity or write-capable API.

A sweep uses (created_at,id) keysets and repeats from the start on completion.
Every source transaction is REPEATABLE READ READ ONLY. Existing records are
refreshed again each sweep; no updated_at timestamp assumptions, no lost ties.
"""

from datetime import datetime, timedelta
from sqlalchemy import func, select, text, tuple_
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


def continuous_paid_end(intervals, at):
    bases = sorted(
        (
            datetime.fromisoformat(i["effective_from"]),
            datetime.fromisoformat(i["effective_until"]),
        )
        for i in intervals
        if i["kind"] == "base"
    )
    current = [end for start, end in bases if start <= at < end]
    if not current:
        past = [end for start, end in bases if end <= at < end + timedelta(hours=72)]
        current = [max(past)] if past else []
    if not current:
        return None
    until = max(current)
    for start, end in bases:
        if start <= until < end:
            until = end
    return until.isoformat()


def read_batch(source, cursor, limit):
    from app.models import Account, Operation
    from app.models.entitlements import EntitlementWorkspace
    from app.services.entitlements import state, usage
    from app.staging import migration_heads

    versions = frozenset(
        source.execute(text("SELECT version_num FROM public.alembic_version")).scalars()
    )
    if versions != migration_heads():
        raise RuntimeError("Warehouse source schema head mismatch")
    public_fields = load_only(
        Account.id,
        Account.name,
        Account.email,
        Account.role,
        Account.workspace_account_id,
        Account.is_active,
        Account.created_at,
        Account.last_login_at,
    )
    query = (
        select(Account)
        .options(public_fields)
        .where(Account.role == "DIRECTOR", Account.workspace_account_id.is_(None))
    )
    if cursor:
        stamp, key = cursor.split("|", 1)
        query = query.where(
            tuple_(Account.created_at, Account.id)
            > tuple_(datetime.fromisoformat(stamp), key)
        )
    owners = list(
        source.scalars(query.order_by(Account.created_at, Account.id).limit(limit))
    )
    ids = [o.id for o in owners]
    workers = (
        list(
            source.scalars(
                select(Account)
                .options(public_fields)
                .where(Account.workspace_account_id.in_(ids))
                .order_by(Account.id)
            )
        )
        if ids
        else []
    )
    activity = (
        dict(
            source.execute(
                select(Operation.account_id, func.max(Operation.created_at))
                .where(Operation.account_id.in_(ids))
                .group_by(Operation.account_id)
            ).all()
        )
        if ids
        else {}
    )
    records = []
    for owner in owners:
        p = source.get(EntitlementWorkspace, owner.id)
        # Reuse the exact product access/quota computation; no copied plan prices.
        access = state(source, owner.id)
        access["continuous_paid_until"] = (
            continuous_paid_end(p.intervals, now()) if p else None
        )
        if not p:
            access["status"] = "UNKNOWN"
        binding = (
            dict(
                id=p.global_binding_id,
                account_id=p.billing_account_id,
                environment=p.source_environment,
            )
            if p and p.global_binding_id
            else None
        )
        people = [owner, *[w for w in workers if w.workspace_account_id == owner.id]]
        records.append(
            dict(
                workspace_id=owner.id,
                display_name=owner.name,
                owner_email=owner.email,
                registered_at=owner.created_at,
                snapshot=dict(
                    source_environment=environment(),
                    access=json_safe(access),
                    usage=usage(source, owner.id),
                    access_authority="warehouse-entitlement-projection"
                    if p
                    else "unavailable",
                    access_incomplete=not bool(p),
                    binding=binding,
                    people=[
                        dict(
                            id=w.id,
                            name=w.name,
                            email=w.email,
                            role=w.role,
                            active=w.is_active,
                            last_login_at=json_safe(w.last_login_at),
                        )
                        for w in people
                    ],
                    business_activity_at=json_safe(activity.get(owner.id)),
                    business_activity_coverage="warehouse stock operations only",
                ),
            )
        )
    next_cursor = (
        owners[-1].created_at.isoformat() + "|" + owners[-1].id
        if len(owners) == limit
        else None
    )
    return records, next_cursor


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
        with Session(connection("CONTROL_CENTER_WAREHOUSE_READ_URL")) as source:
            source.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            # Explicit grants and statement timeout also bound the source role.
            records, cursor = read_batch(source, state.watermark, limit)
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
