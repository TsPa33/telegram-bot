"""Bounded customer directory read model. No CRM, crypto or staff database dependency."""
from datetime import datetime, timedelta
from sqlalchemy import func, select, text, tuple_
from sqlalchemy.orm import load_only
from app.models import now

def json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value

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


def read_batch(source, cursor, limit, source_environment):
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
                    source_environment=source_environment,
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

