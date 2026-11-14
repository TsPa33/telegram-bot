"""Disposable consumer DB only. This is not wired to Warehouse access checks."""

from datetime import datetime
from pathlib import Path
from psycopg2.extras import Json
from .models import BillingError, Conflict, Forbidden
from .service import fingerprint


def validate_snapshot(payload):
    required = {
        "schema_version",
        "event_id",
        "environment",
        "activates_real_services",
        "account_id",
        "workspace_id",
        "product",
        "subscription_id",
        "version",
        "sku",
        "plan_version",
        "limits",
        "paid_intervals",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise BillingError("Invalid snapshot envelope")
    if (
        type(payload["schema_version"]) is not int
        or payload["schema_version"] != 1
        or payload["environment"] != "test"
        or payload["activates_real_services"] is not False
        or type(payload["version"]) is not int
        or payload["version"] < 1
        or type(payload["plan_version"]) is not int
        or payload["plan_version"] < 1
    ):
        raise BillingError("Unsupported snapshot version/environment")
    for key in (
        "event_id",
        "account_id",
        "workspace_id",
        "product",
        "subscription_id",
        "sku",
    ):
        if not isinstance(payload[key], str) or not 1 <= len(payload[key]) <= 160:
            raise BillingError("Invalid snapshot identifier")
    limits = payload["limits"]
    if (
        not isinstance(limits, dict)
        or set(limits) != {"vehicle_capacity", "employees"}
        or any(type(v) is not int or v < 0 for v in limits.values())
    ):
        raise BillingError("Invalid entitlement limits")
    intervals = payload["paid_intervals"]
    if not isinstance(intervals, list) or not intervals:
        raise BillingError("Missing paid intervals")
    previous_end = None
    for interval in intervals:
        if not isinstance(interval, dict) or set(interval) != {"start", "end"}:
            raise BillingError("Invalid paid interval")
        try:
            start, end = (datetime.fromisoformat(interval[k]) for k in ("start", "end"))
            if (
                start.tzinfo is None
                or end.tzinfo is None
                or end <= start
                or previous_end is not None
                and start < previous_end
            ):
                raise ValueError()
            previous_end = end
        except (TypeError, ValueError) as exc:
            raise BillingError("Invalid paid interval") from exc


class Projection:
    def __init__(self, db):
        self.db = db

    def migrate(self):
        with self.db.transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(48151902)")
            cur.execute(
                "SELECT to_regclass('billing_projection.snapshots') AS relation"
            )
            if cur.fetchone()["relation"]:
                return
            cur.execute(
                (Path(__file__).parent / "migrations/001_projection.sql").read_text()
            )

    def provision_fixture_binding(
        self, workspace_id, product, account_id, subscription_id
    ):
        """Trusted consumer-side verification, independent of incoming event fields."""
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO billing_projection.bindings VALUES (%s,%s,%s,%s)",
                (workspace_id, product, account_id, subscription_id),
            )

    def apply(self, payload):
        validate_snapshot(payload)
        digest = fingerprint(payload)
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT * FROM billing_projection.bindings WHERE workspace_id=%s AND product=%s FOR UPDATE",
                (payload["workspace_id"], payload["product"]),
            )
            binding = cur.fetchone()
            if not binding or (binding["account_id"], binding["subscription_id"]) != (
                payload["account_id"],
                payload["subscription_id"],
            ):
                raise Forbidden("Consumer workspace binding mismatch")
            cur.execute(
                "INSERT INTO billing_projection.inbox(event_id,payload_hash) VALUES (%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING event_id",
                (payload["event_id"], digest),
            )
            if not cur.fetchone():
                cur.execute(
                    "SELECT payload_hash FROM billing_projection.inbox WHERE event_id=%s",
                    (payload["event_id"],),
                )
                if cur.fetchone()["payload_hash"] != digest:
                    raise Conflict("Projection event identity collision")
                return "duplicate"
            cur.execute(
                "SELECT * FROM billing_projection.snapshots WHERE subscription_id=%s",
                (payload["subscription_id"],),
            )
            old = cur.fetchone()
            if old and old["version"] >= payload["version"]:
                if old["version"] == payload["version"] and old["payload"] != payload:
                    raise Conflict("Conflicting snapshot version")
                return "stale"
            cur.execute(
                "INSERT INTO billing_projection.snapshots VALUES (%s,%s,%s) "
                "ON CONFLICT(subscription_id) DO UPDATE SET version=excluded.version,payload=excluded.payload",
                (payload["subscription_id"], payload["version"], Json(payload)),
            )
            return "applied"


def deliver_pending(finance_db, projection, *, limit=100):
    """At-least-once: consumer commits first; ack is a separate finance transaction.

    A process crash between the two commits causes harmless replay. Multiple
    workers may deliver the same event; consumer inbox/version checks serialize it.
    """
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise BillingError("Invalid batch size")
    with finance_db.transaction() as cur:
        cur.execute(
            "SELECT id,payload FROM billing.outbox WHERE delivered_at IS NULL ORDER BY created_at,id LIMIT %s",
            (limit,),
        )
        events = cur.fetchall()
    for event in events:
        projection.apply(event["payload"])
        with finance_db.transaction() as cur:
            cur.execute(
                "UPDATE billing.outbox SET delivered_at=now() WHERE id=%s AND delivered_at IS NULL",
                (event["id"],),
            )
    return len(events)
