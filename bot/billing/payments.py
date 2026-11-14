"""Verified LiqPay -> canonical atomic financial posting. No fixture event conversion."""

from datetime import timedelta
from uuid import uuid4
import hashlib
from psycopg2.extras import Json
from .global_core import GlobalBilling, utcnow
from .liqpay_provider import LiqPayProvider, Terms
from .models import BillingError, Conflict, Forbidden, Permission
from .service import uid


class Payments:
    def __init__(
        self, core: GlobalBilling, provider: LiqPayProvider, *, checkout_enabled=False
    ):
        if core.db.environment != provider.profile.environment:
            raise BillingError("Storage/provider environment mismatch")
        self.core, self.provider, self.db, self.checkout_enabled = (
            core,
            provider,
            core.db,
            checkout_enabled,
        )

    def _terms(self, row):
        p = self.provider.profile
        if (
            row["environment"],
            row["merchant"],
            row["profile"],
            row["result_url"],
            row["server_url"],
        ) != (p.environment, p.public_key, p.protocol, p.result_url, p.server_url):
            raise Conflict("Payment belongs to another immutable provider contract")
        return Terms(row["order_id"], row["amount_minor"], row["currency"])

    def _row(self, c, order, *, lock=False):
        c.execute(
            "SELECT n.*,i.id AS intent_id,i.provider,i.environment,i.merchant,o.order_id,o.profile,o.result_url,o.server_url,o.expires_at,n.status AS invoice_status,n.id AS invoice_id FROM billing.provider_orders o JOIN billing.intents i ON i.id=o.intent_id JOIN billing.invoices n ON n.id=i.invoice_id WHERE o.order_id=%s"
            + (" FOR UPDATE OF n" if lock else ""),
            (order,),
        )
        row = c.fetchone()
        if not row:
            raise BillingError("Unknown payment order")
        return row

    def checkout(self, actor, invoice_id):
        if not self.checkout_enabled:
            raise BillingError("Checkout is disabled")
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            c.execute(
                "SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE",
                (actor.account_id,),
            )
            c.execute(
                "SELECT n.*,p.ends_at FROM billing.invoices n JOIN billing.periods p ON p.id=n.period_id WHERE n.id=%s AND n.account_id=%s FOR UPDATE OF n",
                (invoice_id, actor.account_id),
            )
            invoice = c.fetchone()
            if not invoice:
                raise Forbidden("Invoice denied")
            if invoice["status"] != "open" or invoice["ends_at"] <= utcnow():
                raise Conflict("Invoice is not collectible")
            c.execute(
                "SELECT * FROM billing.intents WHERE invoice_id=%s", (invoice_id,)
            )
            intent = c.fetchone()
            if intent and intent["provider"] != "liqpay":
                raise Conflict("Invoice already belongs to another provider")
            if not intent:
                intent_id = uid()
                p = self.provider.profile
                c.execute(
                    "INSERT INTO billing.intents VALUES (%s,%s,%s,'liqpay',%s,%s)",
                    (
                        intent_id,
                        actor.account_id,
                        invoice_id,
                        p.environment,
                        p.public_key,
                    ),
                )
                c.execute(
                    "INSERT INTO billing.attempts(id,account_id,intent_id) VALUES (%s,%s,%s)",
                    (uid(), actor.account_id, intent_id),
                )
                c.execute(
                    "INSERT INTO billing.provider_orders(order_id,intent_id,profile,result_url,server_url,expires_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        "carpot-" + p.environment + "-" + uuid4().hex,
                        intent_id,
                        p.protocol,
                        p.result_url,
                        p.server_url,
                        min(utcnow() + timedelta(minutes=30), invoice["ends_at"]),
                    ),
                )
            c.execute(
                "SELECT o.order_id FROM billing.provider_orders o JOIN billing.intents i ON i.id=o.intent_id WHERE i.invoice_id=%s",
                (invoice_id,),
            )
            saved = c.fetchone()
            if not saved:
                raise Conflict("Provider order missing; requires review")
            row = self._row(c, saved["order_id"])
            terms = self._terms(row)
            if row["expires_at"] <= utcnow():
                raise Conflict(
                    "Checkout expired; reconcile before reissuing the invoice"
                )
            return dict(
                order_id=terms.order_id,
                invoice_id=invoice_id,
                amount_minor=terms.amount_minor,
                currency=terms.currency,
                environment=self.db.environment,
                expires_at=row["expires_at"],
                form=self.provider.checkout(terms),
            )

    def callback(self, data, signature):
        payload = self.provider.decode_callback(data, signature)
        return self._receive(
            payload, hashlib.sha256(data.encode("ascii")).hexdigest(), "callback"
        )

    def _review(self, c, row, event, reason, *, unallocated=False):
        transaction = event.transaction_id or "event:" + event.digest
        c.execute(
            "SELECT 1 FROM billing.reconciliation_cases WHERE provider=%s AND transaction_id=%s",
            (event.provider, transaction),
        )
        if c.fetchone():
            return "review"
        if unallocated:
            journal = uid()
            c.execute(
                "INSERT INTO billing.journal_transactions(id,account_id,external_key,currency) VALUES (%s,%s,%s,'UAH')",
                (
                    journal,
                    row["account_id"],
                    "review:" + event.provider + ":" + transaction,
                ),
            )
            for ledger, amount in (
                ("provider_clearing", event.amount_minor),
                ("unallocated_customer_funds", -event.amount_minor),
            ):
                c.execute(
                    "INSERT INTO billing.journal_entries VALUES (%s,%s,%s,%s,%s)",
                    (uid(), journal, row["account_id"], ledger, amount),
                )
        c.execute(
            "INSERT INTO billing.reconciliation_cases(id,account_id,invoice_id,provider,transaction_id,event_id,amount_minor,currency,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,'UAH',%s) ON CONFLICT DO NOTHING",
            (
                uid(),
                row["account_id"],
                row["invoice_id"],
                event.provider,
                transaction,
                event.digest,
                event.amount_minor,
                reason,
            ),
        )
        return "review"

    def _receive(self, payload, digest, source):
        order = payload.get("order_id")
        if not isinstance(order, str):
            raise BillingError("Invalid order")
        with self.db.transaction() as c:
            initial = self._row(c, order)
            c.execute(
                "SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE",
                (initial["account_id"],),
            )
            row = self._row(c, order, lock=True)
            event = self.provider.correlate(payload, self._terms(row), digest=digest)
            c.execute(
                "INSERT INTO billing.provider_evidence(provider,environment,digest,order_id,payment_id,status,classification,source) VALUES ('liqpay',%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING digest",
                (
                    event.environment,
                    event.digest,
                    order,
                    event.transaction_id,
                    event.raw_status,
                    event.status,
                    source,
                ),
            )
            if not c.fetchone():
                return "duplicate"
            c.execute(
                "INSERT INTO billing.webhook_inbox(provider,event_id,payload_hash,account_id,intent_id,status) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    event.provider,
                    event.digest,
                    event.digest,
                    row["account_id"],
                    row["intent_id"],
                    "pending" if event.status == "review" else event.status,
                ),
            )
            c.execute(
                "SELECT * FROM billing.settlements WHERE invoice_id=%s",
                (row["invoice_id"],),
            )
            settled = c.fetchone()
            if event.status != "success":
                if event.status == "review":
                    return self._review(
                        c, row, event, "provider_status:" + event.raw_status
                    )
                if not settled and event.status == "failure":
                    c.execute(
                        "UPDATE billing.attempts SET status='failed' WHERE intent_id=%s",
                        (row["intent_id"],),
                    )
                return "already_settled" if settled else event.status
            c.execute(
                "INSERT INTO billing.provider_transactions VALUES ('liqpay',%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    event.environment,
                    event.merchant,
                    event.transaction_id,
                    row["intent_id"],
                ),
            )
            c.execute(
                "SELECT intent_id FROM billing.provider_transactions WHERE provider='liqpay' AND environment=%s AND merchant=%s AND payment_id=%s",
                (event.environment, event.merchant, event.transaction_id),
            )
            if c.fetchone()["intent_id"] != row["intent_id"]:
                return self._review(c, row, event, "provider_transaction_reused")
            if settled:
                if settled["transaction_id"] == event.transaction_id:
                    return "already_settled"
                return self._review(c, row, event, "excess_payment", unallocated=True)
            if row["invoice_status"] != "open" or row["expires_at"] <= utcnow():
                return self._review(
                    c, row, event, "uncollectible_invoice", unallocated=True
                )
            # Plan changes become authoritative only together with verified money.
            if row["kind"] == "base":
                c.execute(
                    "SELECT sku,plan_version FROM billing.invoice_lines WHERE invoice_id=%s",
                    (row["invoice_id"],),
                )
                plan = c.fetchone()
                c.execute(
                    "UPDATE billing.subscriptions s SET sku=%s,plan_version=%s FROM billing.periods p WHERE p.id=%s AND s.id=p.subscription_id",
                    (plan["sku"], plan["plan_version"], row["period_id"]),
                )
            return self.core._settle(c, row, event)

    def status(self, actor, order):
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.VIEW)
            row = self._row(c, order)
            if row["account_id"] != actor.account_id:
                raise Forbidden("Order denied")
            self._terms(row)
            c.execute(
                "SELECT 1 FROM billing.settlements WHERE invoice_id=%s",
                (row["invoice_id"],),
            )
            settled = bool(c.fetchone())
            c.execute(
                "SELECT 1 FROM billing.outbox o JOIN billing.periods p ON p.subscription_id=o.aggregate_id WHERE p.id=%s AND o.delivered_at IS NULL LIMIT 1",
                (row["period_id"],),
            )
            pending = bool(c.fetchone())
            c.execute(
                "SELECT 1 FROM billing.reconciliation_cases WHERE invoice_id=%s",
                (row["invoice_id"],),
            )
            review = bool(c.fetchone())
            return dict(
                order_id=order,
                invoice_id=row["invoice_id"],
                amount_minor=row["amount_minor"],
                currency=row["currency"],
                paid=settled,
                activation_pending=settled and pending,
                status="paid"
                if settled
                else "review"
                if review
                else "expired"
                if row["expires_at"] <= utcnow()
                else "pending",
                environment=row["environment"],
            )

    def reconcile(self, actor, order):
        self.status(actor, order)  # tenant/financial authorization before network I/O
        with self.db.transaction() as c:
            row = self._row(c, order)
            terms = self._terms(row)
        payload, digest = self.provider.query_status(terms)
        self._receive(payload, digest, "status")
        return self.status(actor, order)
