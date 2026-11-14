"""Separately gated candidate recurring contract. Never launches automatic charges.

The merchant must confirm per-cycle order correlation, provider subscription identity,
callback fields and cancellation semantics before this profile can be enabled.
"""

import hashlib, re
from datetime import datetime, timezone
from .service import uid
from .global_core import utcnow
from .models import BillingError, Conflict, Forbidden, Permission

CONSENT_VERSION = "carpot-recurring-v1"


class Recurring:
    def __init__(self, core, payments, *, enabled=False, contract_confirmed=False):
        self.core, self.payments, self.db = core, payments, core.db
        self.enabled, self.confirmed = enabled, contract_confirmed

    def gate(self):
        p = self.payments.provider.profile
        if not self.enabled or not self.confirmed or not p.merchant_confirmed:
            raise BillingError(
                "Recurring merchant capability and per-cycle contract not confirmed"
            )

    def consent(
        self, actor, binding, sku, request_key, *, accepted=False, version=None
    ):
        self.gate()
        if (
            accepted is not True
            or version != CONSENT_VERSION
            or not isinstance(request_key, str)
            or not 1 <= len(request_key) <= 160
        ):
            raise BillingError("Explicit versioned recurring consent required")
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            c.execute(
                "SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE",
                (actor.account_id,),
            )
            b, p, s = self.core._subscription(c, actor, binding, sku)
            if b["product"] != "warehouse" or p["kind"] != "base":
                raise BillingError(
                    "Only approved calendar-month base subscriptions support this candidate profile"
                )
            c.execute(
                "SELECT * FROM billing.recurring_mandates WHERE account_id=%s AND request_key=%s",
                (actor.account_id, request_key),
            )
            old = c.fetchone()
            if old:
                if (old["binding_id"], old["sku"], old["consent_version"]) != (
                    binding,
                    sku,
                    version,
                ):
                    raise Conflict("Recurring consent key conflict")
                return dict(old)
            c.execute(
                "SELECT 1 FROM billing.recurring_mandates WHERE binding_id=%s AND state<>'canceled'",
                (binding,),
            )
            if c.fetchone():
                raise Conflict(
                    "Cancel the existing provider mandate before changing tariff"
                )
            c.execute(
                "INSERT INTO billing.recurring_mandates(id,account_id,binding_id,sku,plan_version,consent_version,consented_by,request_key,enrollment_order) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (
                    uid(),
                    actor.account_id,
                    binding,
                    sku,
                    p["version"],
                    version,
                    actor.principal_id,
                    request_key,
                    "carpot-recurring-"
                    + self.db.environment
                    + "-"
                    + uid().replace("-", ""),
                ),
            )
            return dict(c.fetchone())

    def registration(self, actor, mandate):
        self.gate()
        with self.db.transaction() as c:
            row = self._owned(c, actor, mandate)
            if row["state"] != "pending":
                raise Conflict("Mandate registration already resolved")
            c.execute(
                "SELECT amount_minor FROM billing.plan_versions WHERE sku=%s AND version=%s",
                (row["sku"], row["plan_version"]),
            )
            amount = c.fetchone()["amount_minor"]
            c.execute(
                "SELECT max(p.ends_at) AS ends_at FROM billing.periods p JOIN billing.invoices i ON i.period_id=p.id JOIN billing.subscriptions s ON s.id=p.subscription_id WHERE s.binding_id=%s AND i.status='paid' AND i.kind='base'",
                (row["binding_id"],),
            )
            paid = c.fetchone()["ends_at"]
        if not paid or paid <= utcnow():
            raise Conflict(
                "A confirmed first manual payment is required before enrolling recurring"
            )
        p = self.payments.provider.profile
        # Candidate, deliberately distinct from manual pay. Enrolling never grants access.
        payload = dict(
            version=p.version,
            public_key=p.public_key,
            action="subscribe",
            amount=f"{amount // 100}.{amount % 100:02d}",
            currency="UAH",
            order_id=row["enrollment_order"],
            subscribe="1",
            subscribe_periodicity="month",
            subscribe_date_start=paid.strftime("%Y-%m-%d %H:%M:%S"),
            description="Автопродовження CarPot",
            server_url=p.server_url,
            result_url=p.result_url,
        )
        return dict(
            url="https://www.liqpay.ua/api/3/checkout",
            method="POST",
            **self.payments.provider.sign(payload),
        )

    def _owned(self, c, actor, mandate):
        self.core.authorize(c, actor, Permission.MANAGE)
        c.execute(
            "SELECT * FROM billing.recurring_mandates WHERE id=%s AND account_id=%s FOR UPDATE",
            (mandate, actor.account_id),
        )
        row = c.fetchone()
        if not row:
            raise Forbidden("Recurring mandate denied")
        return row

    def callback(self, data, signature):
        self.gate()
        provider = self.payments.provider
        p = provider.profile
        value = provider.decode_callback(data, signature)
        if (
            value.get("public_key") != p.public_key
            or type(value.get("version")) not in (str, int)
            or value.get("version") not in (p.version, str(p.version))
            or value.get("action") != "subscribe"
            or value.get("currency") != "UAH"
        ):
            raise BillingError("Recurring merchant correlation failed")
        if (
            self.db.environment == "production"
            and str(value.get("sandbox", "0")) == "1"
        ):
            raise BillingError("Sandbox mandate cannot activate production")
        pid = value.get("subscription_id")
        if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", pid):
            raise BillingError("Provider subscription identity required")
        digest = hashlib.sha256(data.encode()).hexdigest()
        with self.db.transaction() as c:
            c.execute(
                "SELECT account_id FROM billing.recurring_mandates WHERE enrollment_order=%s",
                (value.get("order_id"),),
            )
            initial = c.fetchone()
            if not initial:
                raise BillingError("Unknown recurring enrollment")
            c.execute(
                "SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE",
                (initial["account_id"],),
            )
            c.execute(
                "SELECT * FROM billing.recurring_mandates WHERE enrollment_order=%s FOR UPDATE",
                (value["order_id"],),
            )
            row = c.fetchone()
            c.execute(
                "SELECT amount_minor FROM billing.plan_versions WHERE sku=%s AND version=%s",
                (row["sku"], row["plan_version"]),
            )
            from .catalogue import money_minor

            if (
                type(value.get("amount")) not in (str, int)
                or money_minor(str(value["amount"])) != c.fetchone()["amount_minor"]
            ):
                raise BillingError("Recurring amount mismatch")
            if row["provider_subscription_id"] not in (None, pid):
                raise BillingError("Recurring identity changed")
            status = value.get("status")
            if status not in {"subscribed", "unsubscribed", "failure", "error"}:
                raise BillingError("Recurring status requires contract review")
            c.execute(
                "INSERT INTO billing.recurring_events(digest,mandate_id,status) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING digest",
                (digest, row["id"], status),
            )
            if not c.fetchone():
                return "duplicate"
            if status == "subscribed" and row["state"] == "pending":
                try:
                    next_at = datetime.fromisoformat(value["next_payment_at"])
                except (ValueError, TypeError, KeyError):
                    raise BillingError("Verified next cycle date required") from None
                if not next_at.tzinfo or next_at <= utcnow():
                    raise BillingError("Verified next cycle date required")
                c.execute(
                    "UPDATE billing.recurring_mandates SET provider_subscription_id=%s,state='active',next_payment_at=%s WHERE id=%s",
                    (pid, next_at, row["id"]),
                )
            elif status == "subscribed" and row["state"] == "cancel_requested":
                c.execute(
                    "UPDATE billing.recurring_mandates SET provider_subscription_id=%s WHERE id=%s",
                    (pid, row["id"]),
                )
            elif status == "unsubscribed" and row["state"] == "cancel_requested":
                c.execute(
                    "UPDATE billing.recurring_mandates SET state='canceled',next_payment_at=NULL WHERE id=%s",
                    (row["id"],),
                )
            elif status in {"failure", "error"}:
                c.execute(
                    "UPDATE billing.recurring_mandates SET last_failure_at=now() WHERE id=%s",
                    (row["id"],),
                )
            return "recorded_without_payment"

    def prepare_cycle(self, actor, mandate):
        self.gate()
        with self.db.transaction() as c:
            row = self._owned(c, actor, mandate)
            if row["state"] != "active":
                raise Conflict("Recurring is not active")
            next_at = row["next_payment_at"]
            if not next_at:
                raise Conflict("Provider cycle date required")
        invoice = self.core.purchase(
            actor,
            row["binding_id"],
            row["sku"],
            "recurring:" + mandate + ":" + next_at.isoformat(),
            now=next_at,
            recurring_mandate=mandate,
        )
        if invoice["starts_at"] != next_at:
            raise Conflict(
                "Manual renewal overlaps provider cycle; pause and review provider schedule"
            )
        order = self.payments.checkout(
            actor, invoice["id"], collector="recurring", mandate_id=mandate
        )
        with self.db.transaction() as c:
            c.execute(
                "INSERT INTO billing.recurring_cycles VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    mandate,
                    invoice["id"],
                    order["order_id"],
                    invoice["starts_at"],
                    invoice["ends_at"],
                ),
            )
        # Metadata only: no charge or parallel retry. Provider cycle correlation must be confirmed.
        return dict(
            invoice_id=invoice["id"],
            order_id=order["order_id"],
            starts_at=invoice["starts_at"],
            ends_at=invoice["ends_at"],
        )

    def cancel(self, actor, mandate):
        # Cancellation stays available after rollout flags are disabled.
        with self.db.transaction() as c:
            row = self._owned(c, actor, mandate)
            if row["state"] not in {"canceled", "cancel_requested"}:
                c.execute(
                    "UPDATE billing.recurring_mandates SET state='cancel_requested' WHERE id=%s",
                    (mandate,),
                )
            return dict(
                state="canceled" if row["state"] == "canceled" else "cancel_requested",
                provider_confirmed=row["state"] == "canceled",
                paid_access_preserved=True,
            )

    def cancellation_command(self, actor, mandate):
        self.gate()
        with self.db.transaction() as c:
            row = self._owned(c, actor, mandate)
            if row["state"] != "cancel_requested":
                raise Conflict("Cancellation request required")
        p = self.payments.provider.profile
        return self.payments.provider.sign(
            dict(
                version=p.version,
                public_key=p.public_key,
                action="unsubscribe",
                order_id=row["enrollment_order"],
            )
        )
