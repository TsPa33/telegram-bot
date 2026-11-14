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
        self,
        core: GlobalBilling,
        provider: LiqPayProvider,
        *,
        checkout_enabled=False,
        hosted_links=None,
    ):
        self.hosted_links = hosted_links
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

    def checkout(self, actor, invoice_id, *, collector="manual", mandate_id=None):
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
            if collector not in {"manual", "recurring"} or (
                collector == "recurring"
            ) != (mandate_id is not None):
                raise BillingError("Explicit collection ownership required")
            if collector == "recurring":
                c.execute(
                    "SELECT 1 FROM billing.recurring_mandates m JOIN billing.subscriptions s ON s.binding_id=m.binding_id JOIN billing.periods p ON p.subscription_id=s.id WHERE m.id=%s AND m.account_id=%s AND m.state='active' AND p.id=%s",
                    (mandate_id, actor.account_id, invoice["period_id"]),
                )
                if not c.fetchone():
                    raise Forbidden("Active mandate required")
            c.execute(
                "INSERT INTO billing.invoice_collectors VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (invoice_id, collector, mandate_id),
            )
            c.execute(
                "SELECT * FROM billing.invoice_collectors WHERE invoice_id=%s",
                (invoice_id,),
            )
            ownership = c.fetchone()
            if (ownership["method"], ownership["mandate_id"]) != (
                collector,
                mandate_id,
            ):
                raise Conflict("Invoice already belongs to another collection method")
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
                        invoice["ends_at"]
                        if collector == "recurring"
                        else min(utcnow() + timedelta(minutes=30), invoice["ends_at"]),
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
                hosted_url=self.hosted_links.url(terms.order_id, row["expires_at"])
                if self.hosted_links
                else None,
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
        if (
            payload.get("status") in {"refund", "reversed", "chargeback"}
            and self.provider.profile.reversals_confirmed
            and {"refund_id", "refund_amount"} <= set(payload)
        ):
            return self._apply_reversal(payload, digest)
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
                "SELECT m.* FROM billing.recurring_cycles z JOIN billing.recurring_mandates m ON m.id=z.mandate_id WHERE z.invoice_id=%s",
                (row["invoice_id"],),
            )
            mandate = c.fetchone()
            c.execute(
                "SELECT method FROM billing.invoice_collectors WHERE invoice_id=%s",
                (row["invoice_id"],),
            )
            collection = c.fetchone()
            if collection and collection["method"] == "recurring" and not mandate:
                raise BillingError("Cycle registration incomplete; retry callback")
            if (
                mandate
                and payload.get("subscription_id")
                != mandate["provider_subscription_id"]
            ):
                raise BillingError("Recurring provider subscription correlation failed")

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
                if mandate and event.status == "failure":
                    c.execute(
                        "UPDATE billing.recurring_mandates SET last_failure_at=now() WHERE id=%s",
                        (mandate["id"],),
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
            result = self.core._settle(c, row, event)
            if mandate:
                c.execute(
                    "SELECT ends_at FROM billing.periods WHERE id=%s",
                    (row["period_id"],),
                )
                end = c.fetchone()["ends_at"]
                c.execute(
                    "UPDATE billing.recurring_mandates SET next_payment_at=greatest(next_payment_at,%s) WHERE id=%s AND state='active'",
                    (end, mandate["id"]),
                )
            return result

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
            c.execute(
                "SELECT coalesce(sum(r.amount_minor),0) AS refunded FROM billing.reversals r JOIN billing.settlements s ON s.id=r.settlement_id WHERE s.invoice_id=%s",
                (row["invoice_id"],),
            )
            refunded = c.fetchone()["refunded"]
            c.execute(
                "SELECT starts_at,ends_at FROM billing.periods WHERE id=%s",
                (row["period_id"],),
            )
            period = c.fetchone()
            state = (
                "refunded"
                if refunded >= row["amount_minor"]
                else "paid"
                if settled
                else "review"
                if review
                else "expired"
                if row["expires_at"] <= utcnow()
                else "pending"
            )
            return dict(
                order_id=order,
                invoice_id=row["invoice_id"],
                amount_minor=row["amount_minor"],
                currency=row["currency"],
                paid=settled,
                activation_pending=settled and pending,
                status=state,
                environment=row["environment"],
                refunded_minor=refunded,
                effective_from=row["effective_at"] or period["starts_at"],
                effective_until=period["ends_at"],
            )

    def reconcile(self, actor, order):
        self.status(actor, order)  # tenant/financial authorization before network I/O
        with self.db.transaction() as c:
            row = self._row(c, order)
            terms = self._terms(row)
        payload, digest = self.provider.query_status(terms)
        self._receive(payload, digest, "status")
        return self.status(actor, order)

    def reconcile_pending(self, *, limit=50):
        if not self.provider.profile.network_enabled:
            return {"checked": 0, "blocked": "provider_network_disabled"}
        if type(limit) is not int or not 1 <= limit <= 100:
            raise BillingError("Bounded reconciliation required")
        checked = 0
        for _ in range(limit):
            # Hold only polling metadata across network I/O, never an account/invoice lock.
            with self.db.transaction() as c:
                c.execute(
                    "INSERT INTO billing.provider_polling(intent_id) SELECT id FROM billing.intents WHERE provider='liqpay' ON CONFLICT DO NOTHING"
                )
                c.execute(
                    "SELECT o.order_id,p.intent_id FROM billing.provider_polling p JOIN billing.provider_orders o ON o.intent_id=p.intent_id LEFT JOIN billing.settlements s ON s.intent_id=p.intent_id WHERE s.id IS NULL AND p.next_attempt_at<=now() ORDER BY p.next_attempt_at LIMIT 1 FOR UPDATE OF p SKIP LOCKED"
                )
                job = c.fetchone()
                if not job:
                    break
                c.execute(
                    "UPDATE billing.provider_polling SET attempts=attempts+1,next_attempt_at=now()+interval '15 minutes' WHERE intent_id=%s",
                    (job["intent_id"],),
                )
                row = self._row(c, job["order_id"])
                terms = self._terms(row)
                try:
                    payload, digest = self.provider.query_status(terms)
                    # Separate financial transaction: no polling row is needed during settlement.
                    self._receive(payload, digest, "status")
                    checked += 1
                except BillingError:
                    c.execute(
                        "UPDATE billing.provider_polling SET last_error='status_unavailable' WHERE intent_id=%s",
                        (job["intent_id"],),
                    )
        return {"checked": checked}

    def verified_reversal(self, data, signature):
        """Incoming signed reversal only; never initiates a provider refund.

        Require explicit original payment ID, a distinct reversal ID and exact refund
        amount. Missing merchant-specific reversal fields stay in review via callback.
        """
        payload = self.provider.decode_callback(data, signature)
        return self._apply_reversal(payload, hashlib.sha256(data.encode()).hexdigest())

    def _apply_reversal(self, payload, digest):
        if (
            not self.provider.profile.merchant_confirmed
            or not self.provider.profile.reversals_confirmed
        ):
            raise BillingError("Merchant reversal contract is not confirmed")
        order = payload.get("order_id")
        if payload.get("status") not in {"reversed", "chargeback", "refund"}:
            raise BillingError("Explicit reversal evidence required")
        with self.db.transaction() as c:
            row = self._row(c, order)
            self.provider.correlate(payload, self._terms(row), digest=digest)
            c.execute(
                "SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE",
                (row["account_id"],),
            )
            c.execute(
                "SELECT * FROM billing.settlements WHERE invoice_id=%s FOR UPDATE",
                (row["invoice_id"],),
            )
            settlement = c.fetchone()
            if (
                not settlement
                or str(payload.get("payment_id")) != settlement["transaction_id"]
            ):
                raise BillingError("Original settled transaction required")
            from .catalogue import money_minor

            amount = money_minor(str(payload.get("refund_amount", "invalid")))
            external = payload.get("refund_id")
            if (
                not isinstance(external, str)
                or not 1 <= len(external) <= 160
                or amount <= 0
            ):
                raise BillingError("Confirmed merchant reversal identity required")
            c.execute(
                "SELECT * FROM billing.reversals WHERE provider=%s AND provider_event_id=%s",
                (settlement["provider"], external),
            )
            old = c.fetchone()
            if old:
                if (
                    old["settlement_id"] != settlement["id"]
                    or old["amount_minor"] != amount
                ):
                    raise Conflict("Reversal identity conflict")
                return "duplicate"
            c.execute(
                "SELECT coalesce(sum(amount_minor),0) AS refunded FROM billing.reversals WHERE settlement_id=%s",
                (settlement["id"],),
            )
            refunded = c.fetchone()["refunded"]
            if refunded + amount > row["amount_minor"]:
                raise Conflict("Reversal exceeds confirmed payment")
            journal = uid()
            c.execute(
                "INSERT INTO billing.journal_transactions(id,account_id,external_key,currency) VALUES (%s,%s,%s,'UAH')",
                (
                    journal,
                    row["account_id"],
                    "reversal:" + settlement["provider"] + ":" + external,
                ),
            )
            for ledger, value in (
                ("provider_clearing", -amount),
                ("service_obligation", amount),
            ):
                c.execute(
                    "INSERT INTO billing.journal_entries VALUES (%s,%s,%s,%s,%s)",
                    (uid(), journal, row["account_id"], ledger, value),
                )
            c.execute(
                "INSERT INTO billing.reversals(id,settlement_id,provider,provider_event_id,amount_minor,reason,journal_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    uid(),
                    settlement["id"],
                    settlement["provider"],
                    external,
                    amount,
                    "chargeback"
                    if payload["status"] == "chargeback"
                    else "reversal"
                    if payload["status"] == "reversed"
                    else "refund",
                    journal,
                ),
            )
            import os

            if self.db.environment == "sandbox":
                from .referrals import Referrals

                Referrals(self.core, enabled=True).on_reversal(c, settlement)
            c.execute(
                "SELECT p.*,s.binding_id,s.sku,s.plan_version,b.workspace_id,b.product FROM billing.periods p JOIN billing.subscriptions s ON s.id=p.subscription_id JOIN billing.bindings b ON b.id=s.binding_id WHERE p.id=%s FOR UPDATE OF s",
                (row["period_id"],),
            )
            period = c.fetchone()
            c.execute(
                "UPDATE billing.subscriptions SET projection_version=projection_version+1 WHERE id=%s RETURNING projection_version",
                (period["subscription_id"],),
            )
            version = c.fetchone()["projection_version"]
            event_id = uid()
            base = dict(schema_version=2, event_id=event_id, version=version)
            snapshot = self.core.entitlement_payload(c, period, row, base)
            c.execute(
                "INSERT INTO billing.outbox(id,account_id,aggregate_id,version,topic,payload) VALUES (%s,%s,%s,%s,'billing.entitlement.snapshot.v2',%s)",
                (
                    event_id,
                    row["account_id"],
                    period["subscription_id"],
                    version,
                    Json(snapshot),
                ),
            )
            # Referral reversal hook is installed by the separately gated ledger package.
            if hasattr(self.core, "reverse_referral"):
                self.core.reverse_referral(c, settlement["id"])
            return "reversed"
