"""Operational product orchestration over the original accounts/invoices/journal/outbox."""

from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from psycopg2.extras import Json
from .service import Billing, uid, fingerprint
from .models import Actor, Permission, BillingError, Conflict, Forbidden
from .storage import OperationalDatabase
from .warehouse import anchored_month


def utcnow():
    return datetime.now(timezone.utc)


class GlobalBilling(Billing):
    def __init__(self, db):
        if type(db) is not OperationalDatabase:
            raise BillingError("Operational Billing storage required")
        super().__init__(db)

    def seed_catalogue(self):
        super().seed_catalogue()
        from .products import seed

        with self.db.transaction() as c:
            seed(c)

    def bind_owner(self, workspace, principal, product, peer, *, account_id=None):
        if not all(
            isinstance(v, str) and 0 < len(v) <= 160
            for v in (workspace, principal, product, peer)
        ):
            raise BillingError("Trusted stable ownership identity required")
        with self.db.transaction() as c:
            c.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (product + ":" + workspace,),
            )
            c.execute(
                "SELECT b.*,a.owner_principal,a.kind FROM billing.bindings b JOIN billing.accounts a ON a.id=b.account_id WHERE b.product=%s AND b.workspace_id=%s",
                (product, workspace),
            )
            old = c.fetchone()
            if old:
                if (
                    old["owner_principal"] != principal
                    or old["kind"] != "company"
                    or account_id
                    and old["account_id"] != account_id
                ):
                    raise Conflict("Canonical ownership requires review")
                account_id = old["account_id"]
                binding = old["id"]
            else:
                if account_id:
                    actor = Actor(principal, account_id, frozenset({Permission.MANAGE}))
                    self.authorize(c, actor, Permission.MANAGE)
                    c.execute(
                        "SELECT kind,owner_principal FROM billing.accounts WHERE id=%s FOR UPDATE",
                        (account_id,),
                    )
                    a = c.fetchone()
                    if a["kind"] != "company" or a["owner_principal"] != principal:
                        raise Forbidden("Company ownership proof required")
                else:
                    account_id = uid()
                    c.execute(
                        "INSERT INTO billing.accounts(id,owner_principal,kind) VALUES (%s,%s,'company')",
                        (account_id, principal),
                    )
                    c.execute(
                        "INSERT INTO billing.memberships VALUES (%s,%s,%s)",
                        (
                            account_id,
                            principal,
                            [p.value for p in (Permission.VIEW, Permission.MANAGE)],
                        ),
                    )
                binding = uid()
                c.execute(
                    "INSERT INTO billing.bindings(id,account_id,workspace_id,product,evidence_id,verified_by) VALUES (%s,%s,%s,%s,%s,%s)",
                    (binding, account_id, workspace, product, uid(), peer),
                )
            c.execute(
                "INSERT INTO billing.product_links(binding_id,environment,peer) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (binding, self.db.environment, peer),
            )
            c.execute(
                "SELECT environment,peer FROM billing.product_links WHERE binding_id=%s",
                (binding,),
            )
            link = c.fetchone()
            if link["environment"] != self.db.environment or link["peer"] != peer:
                raise Forbidden("Binding peer/environment mismatch")
            return dict(
                account_id=account_id,
                binding_id=binding,
                workspace_id=workspace,
                environment=self.db.environment,
            )

    def _subscription(self, c, actor, binding, sku):
        c.execute(
            "SELECT * FROM billing.bindings WHERE id=%s AND account_id=%s FOR UPDATE",
            (binding, actor.account_id),
        )
        b = c.fetchone()
        c.execute(
            "SELECT * FROM billing.plan_versions WHERE sku=%s ORDER BY version DESC LIMIT 1",
            (sku,),
        )
        p = c.fetchone()
        if not b or not p or p["product"] != b["product"]:
            raise Forbidden("Product binding denied")
        c.execute(
            "SELECT * FROM billing.subscriptions WHERE binding_id=%s FOR UPDATE",
            (binding,),
        )
        s = c.fetchone()
        if not s:
            if p["kind"] != "base":
                raise Conflict("Base subscription required before an add-on")
            c.execute(
                "INSERT INTO billing.subscriptions(id,account_id,binding_id,sku,plan_version) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                (uid(), actor.account_id, binding, p["sku"], p["version"]),
            )
            s = c.fetchone()
        return b, p, s

    def purchase(
        self,
        actor,
        binding,
        sku,
        request_key,
        *,
        quantity=1,
        now=None,
    ):
        stamp = now or utcnow()
        if (
            not isinstance(request_key, str)
            or not 1 <= len(request_key) <= 160
            or type(quantity) is not int
            or not 1 <= quantity <= 1000
        ):
            raise BillingError("Invalid purchase command")
        digest = fingerprint([binding, sku, quantity])
        with self.db.transaction() as c:
            self.authorize(c, actor, Permission.MANAGE)
            c.execute(
                "SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE",
                (actor.account_id,),
            )
            c.execute(
                "SELECT * FROM billing.purchase_requests WHERE account_id=%s AND request_key=%s",
                (actor.account_id, request_key),
            )
            old = c.fetchone()
            if old:
                if old["request_hash"] != digest:
                    raise Conflict("Idempotency key conflict")
                return self._invoice_view(c, actor, old["invoice_id"])
            b, p, s = self._subscription(c, actor, binding, sku)
            if p["kind"] == "base" and quantity != 1:
                raise BillingError("A base plan has quantity one")
            if p["kind"] == "base":
                c.execute(
                    "SELECT i.id,l.sku,i.status FROM billing.invoices i JOIN billing.periods p ON p.id=i.period_id JOIN billing.invoice_lines l ON l.invoice_id=i.id WHERE p.subscription_id=%s AND i.kind='base' AND i.status IN ('draft','open') ORDER BY p.starts_at LIMIT 1 FOR UPDATE OF i",
                    (s["id"],),
                )
                unpaid = c.fetchone()
                if unpaid:
                    if unpaid["sku"] != sku:
                        raise Conflict(
                            "Void the unpaid invoice before changing its plan"
                        )
                    if unpaid["status"] == "draft":
                        c.execute(
                            "UPDATE billing.invoices SET status='open' WHERE id=%s",
                            (unpaid["id"],),
                        )
                    c.execute(
                        "INSERT INTO billing.purchase_requests VALUES (%s,%s,%s,%s)",
                        (actor.account_id, request_key, digest, unpaid["id"]),
                    )
                    return self._invoice_view(c, actor, unpaid["id"])
            if p["kind"] == "addon":
                if p["vehicle_capacity"] * quantity > 1000:
                    raise BillingError("Add-on exceeds the approved projection limit")
                c.execute(
                    "SELECT p.* FROM billing.periods p JOIN billing.invoices i ON i.period_id=p.id WHERE p.subscription_id=%s AND i.kind='base' AND i.status='paid' AND NOT EXISTS(SELECT 1 FROM billing.settlements q WHERE q.invoice_id=i.id AND (SELECT coalesce(sum(r.amount_minor),0) FROM billing.reversals r WHERE r.settlement_id=q.id)>=i.amount_minor) AND p.starts_at<=%s AND p.ends_at>%s ORDER BY p.starts_at DESC LIMIT 1",
                    (s["id"], stamp, stamp),
                )
                period = c.fetchone()
                if not period:
                    raise Conflict("Add-on requires a current paid base period")
                start, end = period["starts_at"], period["ends_at"]
                effective = stamp
                micros = (
                    lambda d: (d.days * 86400 + d.seconds) * 1000000 + d.microseconds
                )
                due = int(
                    (
                        Decimal(p["amount_minor"] * quantity)
                        * micros(end - stamp)
                        / micros(end - start)
                    ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
                )
            else:
                c.execute(
                    "SELECT max(p.ends_at) AS ends_at FROM billing.periods p JOIN billing.invoices i ON i.period_id=p.id WHERE p.subscription_id=%s AND i.kind='base' AND i.status='paid' AND NOT EXISTS(SELECT 1 FROM billing.settlements q WHERE q.invoice_id=i.id AND (SELECT coalesce(sum(r.amount_minor),0) FROM billing.reversals r WHERE r.settlement_id=q.id)>=i.amount_minor)",
                    (s["id"],),
                )
                last = c.fetchone()["ends_at"]
                start = max(stamp, last) if last else stamp
                anchor = s["calendar_anchor"] or start.day
                if b["product"] == "warehouse":
                    end = anchored_month(start, anchor=anchor)
                else:
                    from .products import period_end

                    end = period_end(c, p, start)
                effective = start
                c.execute(
                    "SELECT * FROM billing.periods WHERE subscription_id=%s AND starts_at=%s",
                    (s["id"], start),
                )
                period = c.fetchone()
                if not period:
                    c.execute(
                        "INSERT INTO billing.periods VALUES (%s,%s,%s,%s,%s) RETURNING *",
                        (uid(), actor.account_id, s["id"], start, end),
                    )
                    period = c.fetchone()
                due = p["amount_minor"]
                c.execute(
                    "UPDATE billing.subscriptions SET calendar_anchor=coalesce(calendar_anchor,%s) WHERE id=%s",
                    (anchor, s["id"]),
                )
                c.execute(
                    "SELECT i.id,l.sku FROM billing.invoices i JOIN billing.invoice_lines l ON l.invoice_id=i.id WHERE i.period_id=%s AND i.kind='base' AND i.status<>'void'",
                    (period["id"],),
                )
                existing = c.fetchone()
                if existing:
                    if existing["sku"] != sku:
                        raise Conflict(
                            "Void the unpaid invoice before changing its plan"
                        )
                    invoice = existing["id"]
                    c.execute(
                        "INSERT INTO billing.purchase_requests VALUES (%s,%s,%s,%s)",
                        (actor.account_id, request_key, digest, invoice),
                    )
                    return self._invoice_view(c, actor, invoice)
            if due <= 0:
                raise Conflict("Period is too close to expiry")
            invoice = uid()
            c.execute(
                "INSERT INTO billing.invoices(id,account_id,period_id,request_key,request_hash,amount_minor,currency,kind,effective_at) VALUES (%s,%s,%s,%s,%s,%s,'UAH',%s,%s)",
                (
                    invoice,
                    actor.account_id,
                    period["id"],
                    request_key,
                    digest,
                    due,
                    p["kind"],
                    effective,
                ),
            )
            c.execute(
                "INSERT INTO billing.invoice_lines VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uid(),
                    actor.account_id,
                    invoice,
                    sku,
                    p["version"],
                    quantity,
                    p["amount_minor"],
                    due,
                ),
            )
            c.execute(
                "UPDATE billing.invoices SET status='open' WHERE id=%s", (invoice,)
            )
            c.execute(
                "INSERT INTO billing.purchase_requests VALUES (%s,%s,%s,%s)",
                (actor.account_id, request_key, digest, invoice),
            )
            return self._invoice_view(c, actor, invoice)

    @staticmethod
    def _invoice_view(c, actor, invoice):
        c.execute(
            "SELECT i.*,p.starts_at,p.ends_at FROM billing.invoices i JOIN billing.periods p ON p.id=i.period_id WHERE i.id=%s AND i.account_id=%s",
            (invoice, actor.account_id),
        )
        row = c.fetchone()
        if not row:
            raise Forbidden("Invoice denied")
        c.execute(
            "SELECT sku,plan_version,quantity,amount_minor FROM billing.invoice_lines WHERE invoice_id=%s ORDER BY id",
            (invoice,),
        )
        row = dict(row)
        row["lines"] = [dict(r) for r in c.fetchall()]
        return row

    def entitlement_payload(self, c, period, intent, payload):
        # Original invoice-line versions, never mutable current subscription terms.
        c.execute(
            "SELECT coalesce(i.effective_at,p.starts_at) AS starts_at,p.ends_at,i.kind,l.quantity,v.* FROM billing.periods p JOIN billing.invoices i ON i.period_id=p.id JOIN billing.invoice_lines l ON l.invoice_id=i.id JOIN billing.plan_versions v ON (v.sku,v.version)=(l.sku,l.plan_version) WHERE p.subscription_id=%s AND i.status='paid' AND EXISTS(SELECT 1 FROM billing.settlements q JOIN billing.intents n ON n.id=q.intent_id WHERE q.invoice_id=i.id AND n.environment=%s AND n.provider='liqpay') AND NOT EXISTS(SELECT 1 FROM billing.settlements z WHERE z.invoice_id=i.id AND (SELECT coalesce(sum(r.amount_minor),0) FROM billing.reversals r WHERE r.settlement_id=z.id)>=i.amount_minor) ORDER BY p.starts_at,i.id",
            (period["subscription_id"], self.db.environment),
        )
        intervals = []
        for r in c.fetchall():
            intervals.append(
                dict(
                    kind=r["kind"],
                    plan=r["sku"].split(".")[-1]
                    if r["kind"] == "base"
                    else period["sku"].split(".")[-1],
                    sku=r["sku"],
                    plan_version=r["version"],
                    effective_from=r["starts_at"].isoformat(),
                    effective_until=r["ends_at"].isoformat(),
                    vehicle_capacity=r["vehicle_capacity"] * r["quantity"],
                    employee_seats=r["employees"] * r["quantity"],
                )
            )
        c.execute(
            "SELECT * FROM billing.warehouse_trials WHERE account_id=%s",
            (intent["account_id"],),
        )
        trial = c.fetchone()
        if trial and period["product"] == "warehouse":
            from .catalogue import CATALOGUE

            p = CATALOGUE["warehouse." + trial["plan"]]
            # Paid intervals supersede overlapping trial portions, without moving its deadline.
            first = min(
                (
                    datetime.fromisoformat(i["effective_from"])
                    for i in intervals
                    if i["kind"] == "base"
                ),
                default=trial["ends_at"],
            )
            end = min(trial["ends_at"], first)
            if trial["starts_at"] < end:
                intervals.append(
                    dict(
                        kind="trial",
                        plan=trial["plan"],
                        sku=p.sku,
                        plan_version=p.version,
                        effective_from=trial["starts_at"].isoformat(),
                        effective_until=end.isoformat(),
                        vehicle_capacity=p.vehicle_capacity,
                        employee_seats=p.employees,
                    )
                )
        return dict(
            schema_version=2,
            event_id=payload["event_id"],
            environment=self.db.environment,
            activates_real_services=self.db.environment == "production",
            billing_account_id=intent["account_id"],
            workspace_id=period["workspace_id"],
            product=period["product"],
            subscription_id=period["subscription_id"],
            version=payload["version"],
            intervals=intervals,
            trial_used=bool(trial),
        )

    def cabinet(self, actor, binding):
        with self.db.transaction() as c:
            self.authorize(c, actor, Permission.VIEW)
            c.execute(
                "SELECT * FROM billing.bindings WHERE id=%s AND account_id=%s",
                (binding, actor.account_id),
            )
            b = c.fetchone()
            if not b:
                raise Forbidden("Binding denied")
            c.execute(
                "SELECT * FROM billing.plan_versions WHERE product=%s ORDER BY sku,version DESC",
                (b["product"],),
            )
            plans = [dict(r) for r in c.fetchall()]
            c.execute(
                "SELECT * FROM billing.subscriptions WHERE binding_id=%s", (binding,)
            )
            subscription = c.fetchone()
            c.execute(
                "SELECT i.id,i.amount_minor,i.currency,i.status,i.kind,p.starts_at,p.ends_at FROM billing.invoices i JOIN billing.periods p ON p.id=i.period_id JOIN billing.subscriptions s ON s.id=p.subscription_id WHERE s.binding_id=%s ORDER BY p.starts_at DESC,i.id LIMIT 100",
                (binding,),
            )
            invoices = [dict(r) for r in c.fetchall()]
            c.execute(
                "SELECT s.id,s.invoice_id,s.created_at,i.amount_minor,i.currency,o.order_id,(SELECT l.sku FROM billing.invoice_lines l WHERE l.invoice_id=i.id LIMIT 1) AS sku,(SELECT coalesce(sum(r.amount_minor),0)::bigint FROM billing.reversals r WHERE r.settlement_id=s.id) AS refunded_minor FROM billing.settlements s JOIN billing.invoices i ON i.id=s.invoice_id JOIN billing.intents n ON n.id=s.intent_id LEFT JOIN billing.provider_orders o ON o.intent_id=n.id JOIN billing.periods p ON p.id=i.period_id JOIN billing.subscriptions u ON u.id=p.subscription_id WHERE u.binding_id=%s ORDER BY s.created_at DESC LIMIT 100",
                (binding,),
            )
            payments = [dict(r) for r in c.fetchall()]
            c.execute(
                "SELECT r.id,r.invoice_id,r.created_at,i.amount_minor,i.currency FROM billing.reconciliation_cases r JOIN billing.invoices i ON i.id=r.invoice_id JOIN billing.periods p ON p.id=i.period_id JOIN billing.subscriptions s ON s.id=p.subscription_id WHERE s.binding_id=%s ORDER BY r.created_at DESC LIMIT 100",
                (binding,),
            )
            reviews = [dict(r) for r in c.fetchall()]
            return dict(
                environment=self.db.environment,
                plans=plans,
                subscription=dict(subscription) if subscription else None,
                invoices=invoices,
                payments=payments,
                reviews=reviews,
                can_manage=Permission.MANAGE in actor.permissions,
            )

    def trial(self, actor, binding, plan, *, now=None):
        from .catalogue import CATALOGUE

        if plan not in ("standard", "premium"):
            raise BillingError("Unknown trial plan")
        stamp = now or utcnow()
        with self.db.transaction() as c:
            self.authorize(c, actor, Permission.MANAGE)
            c.execute(
                "SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE",
                (actor.account_id,),
            )
            b, p, s = self._subscription(c, actor, binding, "warehouse." + plan)
            c.execute(
                "SELECT 1 FROM billing.invoices i JOIN billing.periods p ON p.id=i.period_id WHERE p.subscription_id=%s AND i.status='paid' AND i.kind='base' LIMIT 1",
                (s["id"],),
            )
            if c.fetchone():
                raise Conflict("A trial cannot replace paid history")
            c.execute(
                "SELECT * FROM billing.warehouse_trials WHERE account_id=%s",
                (actor.account_id,),
            )
            old = c.fetchone()
            if old and old["ends_at"] <= stamp:
                raise Conflict("Company trial already used")
            if not old:
                c.execute(
                    "INSERT INTO billing.warehouse_trials VALUES (%s,%s,%s,%s) RETURNING *",
                    (actor.account_id, plan, stamp, stamp + timedelta(days=10)),
                )
                old = c.fetchone()
            elif old["plan"] != plan:
                c.execute(
                    "UPDATE billing.warehouse_trials SET plan=%s WHERE account_id=%s",
                    (plan, actor.account_id),
                )
            c.execute(
                "UPDATE billing.subscriptions SET projection_version=projection_version+1 WHERE id=%s RETURNING projection_version",
                (s["id"],),
            )
            version = c.fetchone()["projection_version"]
            event = uid()
            payload = dict(
                schema_version=2,
                event_id=event,
                environment=self.db.environment,
                activates_real_services=self.db.environment == "production",
                billing_account_id=actor.account_id,
                workspace_id=b["workspace_id"],
                product="warehouse",
                subscription_id=s["id"],
                version=version,
                trial_used=True,
                intervals=[
                    dict(
                        kind="trial",
                        plan=plan,
                        sku=p["sku"],
                        plan_version=p["version"],
                        effective_from=old["starts_at"].isoformat(),
                        effective_until=old["ends_at"].isoformat(),
                        vehicle_capacity=p["vehicle_capacity"],
                        employee_seats=p["employees"],
                    )
                ],
            )
            c.execute(
                "INSERT INTO billing.outbox(id,account_id,aggregate_id,version,topic,payload) VALUES (%s,%s,%s,%s,'billing.entitlement.snapshot.v2',%s)",
                (event, actor.account_id, s["id"], version, Json(payload)),
            )
            return dict(deadline=old["ends_at"], version=version)
