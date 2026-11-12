"""Phase 2 local two-database bridge. Finance is the sole trial/rights authority."""

from datetime import datetime, timedelta, timezone
import calendar
from uuid import uuid4
from psycopg2.extras import Json
from .models import BillingError, Conflict
from .catalogue import CATALOGUE
from .transport import Transport


def anchored_month(start, months=1, anchor=None):
    ordinal = start.year * 12 + start.month - 1 + months
    year, month = divmod(ordinal, 12)
    month += 1
    return start.replace(
        year=year,
        month=month,
        day=min(anchor or start.day, calendar.monthrange(year, month)[1]),
    )


def migrate_phase2(db):
    with db.transaction() as c:
        c.execute("SELECT pg_advisory_xact_lock(48151903)")
        c.execute("""CREATE TABLE IF NOT EXISTS billing.warehouse_bindings (
            workspace_id text PRIMARY KEY, account_id text NOT NULL UNIQUE REFERENCES billing.accounts,
            owner_id text NOT NULL, version bigint NOT NULL DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS billing.transport_receipts (
            id text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("""CREATE TABLE IF NOT EXISTS billing.warehouse_trials (
            account_id text PRIMARY KEY REFERENCES billing.accounts, plan text NOT NULL,
            starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS billing.warehouse_outbox (
            id text PRIMARY KEY, workspace_id text NOT NULL REFERENCES billing.warehouse_bindings,
            version bigint NOT NULL, payload jsonb NOT NULL, UNIQUE(workspace_id,version))""")


class WarehouseBridge:
    def __init__(self, db, key):
        self.db = db
        self.owner_transport = Transport(
            key, "warehouse-local", "billing-local", "workspace.bind"
        )
        self.entitlement_transport = Transport(
            key, "billing-local", "warehouse-local", "entitlements.write"
        )

    def bind(self, token):
        e = self.owner_transport.verify(token)
        p = e["payload"]
        with self.db.transaction() as c:
            c.execute(
                "INSERT INTO billing.transport_receipts(id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING id",
                (e["jti"],),
            )
            if not c.fetchone():
                raise Conflict("Binding proof replay")
            c.execute(
                "SELECT * FROM billing.warehouse_bindings WHERE workspace_id=%s FOR UPDATE",
                (p["workspace_id"],),
            )
            old = c.fetchone()
            if old:
                if old["owner_id"] != p["owner_id"]:
                    raise Conflict("Owner changed; manual verification required")
                return old["account_id"]
            account = str(uuid4())
            c.execute(
                "INSERT INTO billing.accounts(id,owner_principal,kind) VALUES (%s,%s,'company')",
                (account, p["owner_id"]),
            )
            c.execute(
                "INSERT INTO billing.warehouse_bindings(workspace_id,account_id,owner_id) VALUES (%s,%s,%s)",
                (p["workspace_id"], account, p["owner_id"]),
            )
            return account

    def trial(self, workspace, account, plan, *, now=None):
        if plan not in ("standard", "premium"):
            raise BillingError("Unknown trial plan")
        start = now or datetime.now(timezone.utc)
        with self.db.transaction() as c:
            c.execute(
                "SELECT * FROM billing.warehouse_bindings WHERE workspace_id=%s AND account_id=%s FOR UPDATE",
                (workspace, account),
            )
            binding = c.fetchone()
            if not binding:
                raise BillingError("Unverified workspace")
            c.execute(
                "SELECT * FROM billing.warehouse_trials WHERE account_id=%s", (account,)
            )
            old = c.fetchone()
            if old:
                if old["ends_at"] <= start:
                    raise Conflict("Trial already used")
                # Selection changes retain the exact original deadline, no new trial.
                if old["plan"] == plan:
                    raise Conflict("Trial already active")
                c.execute(
                    "UPDATE billing.warehouse_trials SET plan=%s WHERE account_id=%s",
                    (plan, account),
                )
                begin, end = old["starts_at"], old["ends_at"]
            else:
                begin, end = start, start + timedelta(days=10)
                c.execute(
                    "INSERT INTO billing.warehouse_trials VALUES (%s,%s,%s,%s)",
                    (account, plan, begin, end),
                )
            limits = CATALOGUE["warehouse." + plan]
            interval = dict(
                plan=plan,
                kind="trial",
                effective_from=begin.isoformat(),
                effective_until=end.isoformat(),
                vehicle_capacity=limits.vehicle_capacity,
                employee_seats=limits.employees,
            )
            c.execute(
                "UPDATE billing.warehouse_bindings SET version=version+1 WHERE workspace_id=%s RETURNING version",
                (workspace,),
            )
            version = c.fetchone()["version"]
            event = str(uuid4())
            payload = dict(
                schema_version=2,
                event_id=event,
                workspace_id=workspace,
                billing_account_id=account,
                version=version,
                environment="test",
                intervals=[interval],
                trial_used=True,
            )
            c.execute(
                "INSERT INTO billing.warehouse_outbox VALUES (%s,%s,%s,%s)",
                (event, workspace, version, Json(payload)),
            )
        return self.entitlement_transport.sign(payload)

    def latest(self, workspace, account):
        with self.db.transaction() as c:
            c.execute(
                "SELECT o.payload FROM billing.warehouse_outbox o JOIN billing.warehouse_bindings b "
                "ON b.workspace_id=o.workspace_id WHERE b.workspace_id=%s AND b.account_id=%s ORDER BY o.version DESC LIMIT 1",
                (workspace, account),
            )
            row = c.fetchone()
            return self.entitlement_transport.sign(row["payload"]) if row else None

    def publish_fixture(self, workspace, account, intervals):
        """Trusted local integration fixture, never exposed by an HTTP route."""
        with self.db.transaction() as c:
            c.execute(
                "UPDATE billing.warehouse_bindings SET version=version+1 WHERE workspace_id=%s AND account_id=%s RETURNING version",
                (workspace, account),
            )
            row = c.fetchone()
            if not row:
                raise BillingError("Unverified workspace")
            event = str(uuid4())
            c.execute(
                "SELECT 1 FROM billing.warehouse_trials WHERE account_id=%s", (account,)
            )
            used = bool(c.fetchone())
            payload = dict(
                schema_version=2,
                event_id=event,
                workspace_id=workspace,
                billing_account_id=account,
                version=row["version"],
                environment="test",
                intervals=intervals,
                trial_used=used,
            )
            c.execute(
                "INSERT INTO billing.warehouse_outbox VALUES (%s,%s,%s,%s)",
                (event, workspace, row["version"], Json(payload)),
            )
        return self.entitlement_transport.sign(payload)
