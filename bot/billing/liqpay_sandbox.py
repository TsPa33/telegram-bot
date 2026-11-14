"""Local-only LiqPay sandbox order/evidence storage. Never settles real invoices.

Uses existing immutable invoice terms and membership authorization. The existing
fixture ledger is not changed. No HTTP route, provider call, entitlement grant or
live database is opened by this module.
"""
from pathlib import Path
from uuid import uuid4

from .db import Database
from .liqpay import CheckoutTerms, SandboxCodec, SandboxContract
from .models import BillingError, Conflict, Forbidden, Permission
from .service import Billing


def migrate_sandbox(db: Database):
    if type(db) is not Database:
        raise BillingError("Explicit disposable finance database required")
    with db.transaction() as c:
        c.execute("SELECT pg_advisory_xact_lock(48151904)")
        c.execute("SELECT to_regclass('billing.liqpay_sandbox_orders') AS relation")
        if c.fetchone()["relation"]:
            return
        c.execute((Path(__file__).parent / "migrations/003_liqpay_sandbox.sql").read_text())


class SandboxCheckout:
    def __init__(self, db: Database, contract: SandboxContract, *, enabled=False):
        if enabled is not True or type(db) is not Database:
            raise BillingError("Sandbox checkout requires explicit disposable finance mode")
        self.db = db
        self.codec = SandboxCodec(contract)

    def _terms(self, row):
        contract = self.codec.contract
        if (row["merchant"], row["version"], row["result_url"], row["server_url"]) != (
            contract.public_key, contract.version, contract.result_url, contract.server_url
        ):
            raise Conflict("Sandbox order belongs to another configured contract")
        return CheckoutTerms(row["id"], row["amount_minor"], row["currency"])

    def create(self, actor, invoice_id):
        """One stable order per open invoice, using server-side immutable price."""
        with self.db.transaction() as c:
            Billing.authorize(c, actor, Permission.MANAGE)
            c.execute("SELECT * FROM billing.invoices WHERE id=%s AND account_id=%s FOR UPDATE",
                      (invoice_id, actor.account_id))
            invoice = c.fetchone()
            if not invoice:
                raise Forbidden("Invoice denied")
            if invoice["status"] != "open":
                raise Conflict("Issued unpaid invoice required")
            c.execute("SELECT id FROM billing.intents WHERE invoice_id=%s", (invoice_id,))
            if c.fetchone():
                raise Conflict("Invoice already has a fixture payment intent")
            c.execute("SELECT * FROM billing.liqpay_sandbox_orders WHERE invoice_id=%s", (invoice_id,))
            row = c.fetchone()
            if not row:
                contract = self.codec.contract
                c.execute("""INSERT INTO billing.liqpay_sandbox_orders
                    (id, account_id, invoice_id, amount_minor, currency, merchant, version, result_url, server_url)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    ("carpot-wh-sbx-" + uuid4().hex, actor.account_id, invoice_id, invoice["amount_minor"],
                     invoice["currency"], contract.public_key, contract.version, contract.result_url, contract.server_url))
                row = c.fetchone()
            terms = self._terms(row)
            return {"order_id": terms.order_id, "amount_minor": terms.amount_minor, "currency": terms.currency,
                    "environment": "sandbox", "activates_real_services": False,
                    "form": self.codec.checkout(terms)}

    def receive(self, data, signature):
        """Verified callback evidence only; does not invoke the fixture settlement path."""
        payload = self.codec.verify(data, signature)
        with self.db.transaction() as c:
            c.execute("SELECT * FROM billing.liqpay_sandbox_orders WHERE id=%s FOR UPDATE",
                      (payload["order_id"],))
            row = c.fetchone()
            if not row:
                raise BillingError("Unknown sandbox order")
            event = self.codec.correlate(data, signature, self._terms(row))
            c.execute("""SELECT 1 FROM billing.liqpay_sandbox_events
                      WHERE order_id=%s AND digest=%s""", (event.order_id, event.digest))
            if c.fetchone():
                return "duplicate"
            classification = event.classification
            if classification == "test_success":
                c.execute("""INSERT INTO billing.liqpay_sandbox_payment_ids (merchant,payment_id,order_id)
                           VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                          (event.merchant, event.payment_id, event.order_id))
                c.execute("""SELECT order_id FROM billing.liqpay_sandbox_payment_ids
                           WHERE merchant=%s AND payment_id=%s""", (event.merchant, event.payment_id))
                if c.fetchone()["order_id"] != event.order_id:
                    classification = "review"
                c.execute("""SELECT 1 FROM billing.liqpay_sandbox_events WHERE order_id=%s
                           AND classification='test_success' AND payment_id<>%s LIMIT 1""",
                          (event.order_id, event.payment_id))
                if c.fetchone():
                    classification = "review"
            c.execute("""INSERT INTO billing.liqpay_sandbox_events
                       (order_id,digest,payment_id,provider_status,classification,amount_minor)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                      (event.order_id, event.digest, event.payment_id, event.provider_status,
                       classification, event.amount_minor))
            return classification

    def status(self, actor, order_id):
        with self.db.transaction() as c:
            Billing.authorize(c, actor, Permission.VIEW)
            c.execute("SELECT * FROM billing.liqpay_sandbox_orders WHERE id=%s AND account_id=%s",
                      (order_id, actor.account_id))
            row = c.fetchone()
            if not row:
                raise Forbidden("Sandbox order denied")
            terms = self._terms(row)
            c.execute("""SELECT provider_status,classification,payment_id FROM billing.liqpay_sandbox_events
                      WHERE order_id=%s ORDER BY received_at,digest""", (order_id,))
            events = [dict(x) for x in c.fetchall()]
            classes = {x["classification"] for x in events}
            # Late failure or pending cannot undo test success; review needs attention.
            state = next((x for x in ("review", "test_success", "failed", "pending") if x in classes), "created")
            return {"order_id": order_id, "amount_minor": terms.amount_minor, "currency": terms.currency,
                    "status": state, "environment": "sandbox", "activates_real_services": False,
                    "events": events, "status_request": self.codec.status_request(terms)}
