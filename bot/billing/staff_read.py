"""Narrow Warehouse read peer. No customer membership or financial mutation."""

import hashlib
import os
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool
from .models import BillingError
from .transport import Transport


def register(app, db, peer_keys, limiter):
    @app.get("/v1/staff/warehouse/{binding}")
    async def warehouse_read(binding: str, request: Request):
        if os.getenv("BILLING_STAFF_READ_ENABLED", "false") != "true":
            raise HTTPException(404)
        if (
            request.headers.get("X-CarPot-Peer") != "control-center"
            or "control-center" not in peer_keys
        ):
            raise HTTPException(401)
        limiter.acquire()
        if any(
            key == peer_keys["control-center"]
            for name, key in peer_keys.items()
            if name != "control-center"
        ):
            raise HTTPException(503, "Dedicated staff peer key required")
        body = await request.body()
        authorization = request.headers.get("Authorization", "")
        if body or len(binding) > 80 or not authorization.startswith("Bearer "):
            raise HTTPException(401)

        def read():
            try:
                e = Transport(
                    peer_keys["control-center"],
                    "control-center",
                    "billing-api",
                    "billing.staff.read",
                    environment=db.environment,
                ).verify(authorization[7:])
                p = e["payload"]
                if (
                    not isinstance(p, dict)
                    or p.get("scope") != "warehouse.finance.read"
                    or p.get("method") != "GET"
                    or p.get("path") != request.url.path
                    or p.get("body_sha256") != hashlib.sha256(b"").hexdigest()
                    or p.get("binding_id") != binding
                ):
                    raise BillingError("Staff request scope mismatch")
                with db.transaction() as c:
                    c.execute(
                        "INSERT INTO billing.api_receipts VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING nonce",
                        (
                            "control-center",
                            e["jti"],
                            datetime.fromtimestamp(e["exp"], timezone.utc),
                        ),
                    )
                    if not c.fetchone():
                        raise BillingError("Staff transport replay")
                    c.execute(
                        "SELECT b.id FROM billing.bindings b JOIN billing.product_links l ON l.binding_id=b.id WHERE b.id=%s AND b.product='warehouse' AND b.workspace_id=%s AND l.environment=%s",
                        (binding, p.get("workspace_id"), db.environment),
                    )
                    if not c.fetchone():
                        return None
                    c.execute(
                        "SELECT i.id,i.status,i.amount_minor,i.currency,i.kind,p.starts_at,p.ends_at FROM billing.invoices i JOIN billing.periods p ON p.id=i.period_id JOIN billing.subscriptions s ON s.id=p.subscription_id WHERE s.binding_id=%s ORDER BY p.starts_at DESC,i.id LIMIT 100",
                        (binding,),
                    )
                    invoices = [dict(r) for r in c.fetchall()]
                    c.execute(
                        "SELECT s.id,s.invoice_id,s.created_at,i.amount_minor,i.currency,(SELECT coalesce(sum(r.amount_minor),0)::bigint FROM billing.reversals r WHERE r.settlement_id=s.id) AS refunded_minor FROM billing.settlements s JOIN billing.invoices i ON i.id=s.invoice_id JOIN billing.intents n ON n.id=s.intent_id JOIN billing.periods p ON p.id=i.period_id JOIN billing.subscriptions u ON u.id=p.subscription_id WHERE u.binding_id=%s AND n.provider='liqpay' AND n.environment=%s ORDER BY s.created_at DESC,s.id LIMIT 100",
                        (binding, db.environment),
                    )
                    payments = [dict(r) for r in c.fetchall()]
                    c.execute(
                        "SELECT r.id,r.amount_minor,r.created_at,r.settlement_id FROM billing.reversals r JOIN billing.settlements s ON s.id=r.settlement_id JOIN billing.invoices i ON i.id=s.invoice_id JOIN billing.periods p ON p.id=i.period_id JOIN billing.subscriptions u ON u.id=p.subscription_id WHERE u.binding_id=%s ORDER BY r.created_at DESC,r.id LIMIT 100",
                        (binding,),
                    )
                    reversals = [dict(r) for r in c.fetchall()]
                    c.execute(
                        "SELECT r.id,r.invoice_id,r.reason,r.created_at FROM billing.reconciliation_cases r JOIN billing.invoices i ON i.id=r.invoice_id JOIN billing.periods p ON p.id=i.period_id JOIN billing.subscriptions s ON s.id=p.subscription_id WHERE s.binding_id=%s ORDER BY r.created_at DESC,r.id LIMIT 100",
                        (binding,),
                    )
                    reviews = [dict(r) for r in c.fetchall()]
                    c.execute(
                        "SELECT o.payload FROM billing.outbox o JOIN billing.subscriptions s ON s.id=o.aggregate_id WHERE s.binding_id=%s ORDER BY o.version DESC LIMIT 1",
                        (binding,),
                    )
                    snapshot = c.fetchone()
                    periods = [
                        i
                        for i in (
                            snapshot["payload"].get("intervals", []) if snapshot else []
                        )
                        if i.get("kind") == "base"
                    ]
                    return dict(
                        binding_id=binding,
                        environment=db.environment,
                        invoices=invoices,
                        payments=payments,
                        paid_periods=periods,
                        reversals=reversals,
                        reviews=reviews,
                        coverage="bounded_latest_100_per_section",
                        totals_available=False,
                    )
            except BillingError:
                raise HTTPException(401, "Invalid staff read authorization") from None

        result = await run_in_threadpool(read)
        if result is None:
            raise HTTPException(403, "Warehouse binding denied")
        return result
