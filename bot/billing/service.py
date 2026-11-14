"""Synchronous transaction boundary, designed for a future backend worker/thread pool.

Only disposable fixture mode is executable in Phase 1. No legacy imports, network,
real service activation, provider calls or automatic connection discovery.
"""

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from uuid import uuid4
from psycopg2.extras import Json
from .catalogue import CATALOGUE
from .db import Database
from .models import (
    Actor,
    BillingError,
    Conflict,
    Forbidden,
    Permission,
    VerifiedBinding,
)
from .providers import FixtureAdapter, ProviderEvent, PaymentAdapter


def uid():
    return str(uuid4())


def fingerprint(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Billing:
    def __init__(self, db: Database, adapter: PaymentAdapter | None = None):
        self.db = db
        self.adapter = adapter or FixtureAdapter()
        if self.adapter.name != "fixture" or self.adapter.environment != "test":
            raise BillingError(
                "Only the isolated fixture adapter is executable in Phase 1"
            )

    @staticmethod
    def authorize(cur, actor: Actor, permission: Permission):
        cur.execute(
            "SELECT permissions FROM billing.memberships WHERE account_id=%s AND principal_id=%s FOR SHARE",
            (actor.account_id, actor.principal_id),
        )
        member = cur.fetchone()
        if (
            not member
            or permission not in actor.permissions
            or permission.value not in member["permissions"]
        ):
            raise Forbidden("Financial permission denied")

    def provision_fixture_account(self, owner: str, *, kind: str = "company") -> Actor:
        """Trusted fixture provisioning, not a public registration endpoint."""
        account = uid()
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO billing.accounts(id,owner_principal,kind) VALUES (%s,%s,%s)",
                (account, owner, kind),
            )
            cur.execute(
                "INSERT INTO billing.memberships VALUES (%s,%s,%s)",
                (account, owner, [p.value for p in Permission]),
            )
        return Actor(owner, account, frozenset(Permission))

    def seed_catalogue(self):
        with self.db.transaction() as cur:
            for p in CATALOGUE.values():
                cur.execute(
                    "INSERT INTO billing.plan_versions VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT DO NOTHING",
                    (
                        p.sku,
                        p.version,
                        p.product,
                        p.kind,
                        p.amount_minor,
                        p.currency,
                        p.vehicle_capacity,
                        p.employees,
                    ),
                )
                cur.execute(
                    "SELECT * FROM billing.plan_versions WHERE sku=%s AND version=%s",
                    (p.sku, p.version),
                )
                stored = cur.fetchone()
                if any(stored[k] != v for k, v in asdict(p).items()):
                    raise Conflict("Catalogue version collision; publish a new version")

    def bind(self, actor: Actor, evidence: VerifiedBinding) -> str:
        if (
            not evidence.evidence_id
            or not evidence.verified_by
            or not evidence.workspace_id
        ):
            raise BillingError("Verified ownership evidence required")
        if evidence.product != "warehouse":
            raise BillingError("Only Warehouse fixture bindings supported in Phase 1")
        with self.db.transaction() as cur:
            self.authorize(cur, actor, Permission.MANAGE)
            cur.execute(
                "SELECT kind FROM billing.accounts WHERE id=%s", (actor.account_id,)
            )
            if cur.fetchone()["kind"] != "company":
                raise Forbidden(
                    "Company workspace cannot bind to a personal bonus account"
                )
            binding = uid()
            cur.execute(
                "INSERT INTO billing.bindings(id,account_id,workspace_id,product,evidence_id,verified_by) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    binding,
                    actor.account_id,
                    evidence.workspace_id,
                    evidence.product,
                    evidence.evidence_id,
                    evidence.verified_by,
                ),
            )
            return binding

    def subscribe(self, actor: Actor, binding_id: str, sku: str) -> str:
        if sku not in CATALOGUE or CATALOGUE[sku].kind != "base":
            raise BillingError("Base plan required")
        p = CATALOGUE[sku]
        with self.db.transaction() as cur:
            self.authorize(cur, actor, Permission.MANAGE)
            cur.execute(
                "SELECT * FROM billing.bindings WHERE id=%s AND account_id=%s FOR UPDATE",
                (binding_id, actor.account_id),
            )
            binding = cur.fetchone()
            if not binding or binding["product"] != p.product:
                raise Forbidden("Workspace binding denied")
            subscription = uid()
            cur.execute(
                "INSERT INTO billing.subscriptions(id,account_id,binding_id,sku,plan_version) "
                "VALUES (%s,%s,%s,%s,%s)",
                (subscription, actor.account_id, binding_id, sku, p.version),
            )
            return subscription

    def create_invoice(
        self,
        actor: Actor,
        subscription_id: str,
        start: datetime,
        end: datetime,
        request_key: str,
    ) -> str:
        if not isinstance(request_key, str) or not 1 <= len(request_key) <= 160:
            raise BillingError("Invalid idempotency key")
        # ISO-UTC timestamps prevent equivalent offsets from changing idempotency semantics.
        from datetime import timezone

        if (
            any(t.tzinfo is None or t.utcoffset() is None for t in (start, end))
            or end <= start
        ):
            raise BillingError("Invalid period")
        start, end = (t.astimezone(timezone.utc) for t in (start, end))
        request_hash = fingerprint(
            [subscription_id, start.isoformat(), end.isoformat()]
        )
        with self.db.transaction() as cur:
            self.authorize(cur, actor, Permission.MANAGE)
            # Account lock serializes idempotency keys across different subscriptions.
            cur.execute(
                "SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE",
                (actor.account_id,),
            )
            cur.execute(
                "SELECT * FROM billing.invoices WHERE account_id=%s AND request_key=%s",
                (actor.account_id, request_key),
            )
            existing = cur.fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise Conflict("Idempotency key reused with different terms")
                return existing["id"]
            cur.execute(
                "SELECT s.*,p.amount_minor,p.currency FROM billing.subscriptions s "
                "JOIN billing.plan_versions p ON (p.sku,p.version)=(s.sku,s.plan_version) "
                "WHERE s.id=%s AND s.account_id=%s FOR UPDATE OF s",
                (subscription_id, actor.account_id),
            )
            sub = cur.fetchone()
            if not sub:
                raise Forbidden("Subscription denied")
            from .warehouse import anchored_month

            anchor = sub.get("calendar_anchor") or start.day
            if end != anchored_month(start, anchor=anchor):
                raise BillingError(
                    "A base invoice must cover exactly one anchored calendar month"
                )
            if "calendar_anchor" in sub and sub["calendar_anchor"] is None:
                cur.execute(
                    "UPDATE billing.subscriptions SET calendar_anchor=%s WHERE id=%s",
                    (anchor, subscription_id),
                )
            cur.execute(
                "SELECT to_regclass('billing.reconciliation_cases') AS relation"
            )
            phase2 = bool(cur.fetchone()["relation"])
            cur.execute(
                "SELECT p.id,p.starts_at,p.ends_at FROM billing.periods p WHERE subscription_id=%s AND starts_at<%s AND ends_at>%s",
                (subscription_id, end, start),
            )
            overlaps = cur.fetchall()
            period = None
            for existing_period in overlaps:
                cur.execute(
                    "SELECT 1 FROM billing.invoices WHERE period_id=%s AND status<>'void'",
                    (existing_period["id"],),
                )
                collectible = cur.fetchone()
                if (
                    not phase2
                    or collectible
                    or existing_period["starts_at"] != start
                    or existing_period["ends_at"] != end
                ):
                    raise Conflict("Overlapping billing period")
                period = existing_period["id"]
            invoice = uid()
            if period is None:
                period = uid()
                cur.execute(
                    "INSERT INTO billing.periods VALUES (%s,%s,%s,%s,%s)",
                    (period, actor.account_id, subscription_id, start, end),
                )
            cur.execute(
                "INSERT INTO billing.invoices(id,account_id,period_id,request_key,request_hash,amount_minor,currency) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    invoice,
                    actor.account_id,
                    period,
                    request_key,
                    request_hash,
                    sub["amount_minor"],
                    sub["currency"],
                ),
            )
            cur.execute(
                "INSERT INTO billing.invoice_lines VALUES (%s,%s,%s,%s,%s,1,%s,%s)",
                (
                    uid(),
                    actor.account_id,
                    invoice,
                    sub["sku"],
                    sub["plan_version"],
                    sub["amount_minor"],
                    sub["amount_minor"],
                ),
            )
            return invoice

    def transition_invoice(self, actor: Actor, invoice: str, target: str):
        if target not in {"open", "void"}:
            raise BillingError("Only issue/void transitions are public commands")
        with self.db.transaction() as cur:
            self.authorize(cur, actor, Permission.MANAGE)
            cur.execute(
                "SELECT * FROM billing.invoices WHERE id=%s AND account_id=%s FOR UPDATE",
                (invoice, actor.account_id),
            )
            row = cur.fetchone()
            if not row:
                raise Forbidden("Invoice denied")
            if row["status"] == target:
                return
            if row["status"] not in (
                {"draft"} if target == "open" else {"draft", "open"}
            ):
                raise Conflict("Invalid invoice transition")
            cur.execute("SELECT 1 FROM billing.intents WHERE invoice_id=%s", (invoice,))
            if target == "void" and cur.fetchone():
                raise Conflict(
                    "Cannot void an invoice with an outstanding payment intent"
                )
            cur.execute(
                "UPDATE billing.invoices SET status=%s WHERE id=%s", (target, invoice)
            )

    def create_intent(self, actor: Actor, invoice: str) -> str:
        with self.db.transaction() as cur:
            self.authorize(cur, actor, Permission.MANAGE)
            cur.execute(
                "SELECT * FROM billing.invoices WHERE id=%s AND account_id=%s FOR UPDATE",
                (invoice, actor.account_id),
            )
            row = cur.fetchone()
            if not row:
                raise Forbidden("Invoice denied")
            if row["status"] != "open":
                raise Conflict("Issued unpaid invoice required")
            cur.execute(
                "SELECT id FROM billing.intents WHERE invoice_id=%s", (invoice,)
            )
            existing = cur.fetchone()
            if existing:
                return existing["id"]
            intent = uid()
            cur.execute(
                "INSERT INTO billing.intents VALUES (%s,%s,%s,'fixture','test','disposable-fixture')",
                (intent, actor.account_id, invoice),
            )
            cur.execute(
                "INSERT INTO billing.attempts(id,account_id,intent_id) VALUES (%s,%s,%s)",
                (uid(), actor.account_id, intent),
            )
            return intent

    def receive_fixture(self, event: ProviderEvent) -> str:
        """Verify -> lock invoice -> inbox -> settlement+journal+outbox in one commit.

        Only callable in local fixture storage; no HTTP route is registered.
        A failed/pending event never demotes confirmed money or entitlements.
        """
        self.adapter.verify(event)
        digest = fingerprint(asdict(event))
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT i.*,n.amount_minor,n.currency,n.status AS invoice_status,n.period_id "
                "FROM billing.intents i JOIN billing.invoices n ON n.id=i.invoice_id "
                "WHERE i.id=%s FOR UPDATE OF n",
                (event.intent_id,),
            )
            intent = cur.fetchone()
            if not intent:
                raise BillingError("Unknown intent")
            if (
                event.amount_minor != intent["amount_minor"]
                or event.currency != intent["currency"]
                or event.merchant != intent["merchant"]
                or event.environment != intent["environment"]
            ):
                raise BillingError("Provider terms mismatch")
            cur.execute(
                "INSERT INTO billing.webhook_inbox VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING event_id",
                (
                    event.provider,
                    event.event_id,
                    digest,
                    intent["account_id"],
                    event.intent_id,
                    event.status,
                ),
            )
            if not cur.fetchone():
                cur.execute(
                    "SELECT payload_hash FROM billing.webhook_inbox WHERE provider=%s AND event_id=%s",
                    (event.provider, event.event_id),
                )
                if cur.fetchone()["payload_hash"] != digest:
                    raise Conflict("Provider event identity collision")
                return "duplicate"
            cur.execute(
                "SELECT transaction_id FROM billing.settlements WHERE invoice_id=%s",
                (intent["invoice_id"],),
            )
            settled = cur.fetchone()
            if settled:
                if (
                    event.status == "success"
                    and settled["transaction_id"] != event.transaction_id
                ):
                    cur.execute(
                        "SELECT to_regclass('billing.reconciliation_cases') AS relation"
                    )
                    if not cur.fetchone()["relation"]:
                        raise Conflict(
                            "Second external payment requires reconciliation"
                        )
                    cur.execute(
                        "INSERT INTO billing.reconciliation_cases(id,account_id,invoice_id,provider,transaction_id,event_id,amount_minor,currency,reason) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'excess_payment') ON CONFLICT DO NOTHING",
                        (
                            uid(),
                            intent["account_id"],
                            intent["invoice_id"],
                            event.provider,
                            event.transaction_id,
                            event.event_id,
                            event.amount_minor,
                            event.currency,
                        ),
                    )
                    return "reconciliation_required"
                return "already_settled"
            if event.status != "success":
                # Pending after failure cannot reopen or alter a settled invoice.
                if event.status == "failure":
                    cur.execute(
                        "UPDATE billing.attempts SET status='failed' WHERE intent_id=%s",
                        (event.intent_id,),
                    )
                return event.status
            if intent["invoice_status"] != "open":
                raise Conflict("Invoice is not collectible")
            journal = uid()
            cur.execute(
                "INSERT INTO billing.journal_transactions(id,account_id,external_key,currency) VALUES (%s,%s,%s,%s)",
                (
                    journal,
                    intent["account_id"],
                    f"{event.provider}:{event.transaction_id}",
                    event.currency,
                ),
            )
            for ledger, amount in (
                ("provider_clearing", event.amount_minor),
                ("service_obligation", -event.amount_minor),
            ):
                cur.execute(
                    "INSERT INTO billing.journal_entries VALUES (%s,%s,%s,%s,%s)",
                    (uid(), journal, intent["account_id"], ledger, amount),
                )
            cur.execute(
                "INSERT INTO billing.settlements(id,account_id,invoice_id,intent_id,provider,transaction_id,journal_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    uid(),
                    intent["account_id"],
                    intent["invoice_id"],
                    event.intent_id,
                    event.provider,
                    event.transaction_id,
                    journal,
                ),
            )
            cur.execute(
                "UPDATE billing.invoices SET status='paid' WHERE id=%s",
                (intent["invoice_id"],),
            )
            cur.execute(
                "UPDATE billing.attempts SET status='confirmed' WHERE intent_id=%s",
                (event.intent_id,),
            )
            cur.execute(
                "SELECT p.*,s.binding_id,s.sku,s.plan_version,b.workspace_id,b.product "
                "FROM billing.periods p JOIN billing.subscriptions s ON s.id=p.subscription_id "
                "JOIN billing.bindings b ON b.id=s.binding_id WHERE p.id=%s FOR UPDATE OF s",
                (intent["period_id"],),
            )
            period = cur.fetchone()
            cur.execute(
                "UPDATE billing.subscriptions SET status='active',projection_version=projection_version+1 "
                "WHERE id=%s RETURNING projection_version",
                (period["subscription_id"],),
            )
            version = cur.fetchone()["projection_version"]
            cur.execute(
                "SELECT vehicle_capacity,employees FROM billing.plan_versions WHERE sku=%s AND version=%s",
                (period["sku"], period["plan_version"]),
            )
            limits = dict(cur.fetchone())
            # Full snapshot of paid intervals, so late settlement cannot shorten access.
            cur.execute(
                "SELECT p.starts_at,p.ends_at FROM billing.periods p JOIN billing.invoices i "
                "ON i.period_id=p.id WHERE p.subscription_id=%s AND i.status='paid' ORDER BY p.starts_at",
                (period["subscription_id"],),
            )
            intervals = [
                {"start": p["starts_at"].isoformat(), "end": p["ends_at"].isoformat()}
                for p in cur.fetchall()
            ]
            event_id = uid()
            payload = {
                "schema_version": 1,
                "event_id": event_id,
                "environment": "test",
                "activates_real_services": False,
                "account_id": intent["account_id"],
                "workspace_id": period["workspace_id"],
                "product": period["product"],
                "subscription_id": period["subscription_id"],
                "version": version,
                "sku": period["sku"],
                "plan_version": period["plan_version"],
                "limits": limits,
                "paid_intervals": intervals,
            }
            cur.execute(
                "INSERT INTO billing.outbox(id,account_id,aggregate_id,version,topic,payload) "
                "VALUES (%s,%s,%s,%s,'billing.entitlement.snapshot.v1',%s)",
                (
                    event_id,
                    intent["account_id"],
                    period["subscription_id"],
                    version,
                    Json(payload),
                ),
            )
            return "settled"

    def invoice(self, actor: Actor, invoice_id: str):
        with self.db.transaction() as cur:
            self.authorize(cur, actor, Permission.VIEW)
            cur.execute(
                "SELECT * FROM billing.invoices WHERE id=%s AND account_id=%s",
                (invoice_id, actor.account_id),
            )
            result = cur.fetchone()
            if not result:
                raise Forbidden("Invoice denied")
            return dict(result)
