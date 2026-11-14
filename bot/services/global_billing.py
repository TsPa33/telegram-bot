"""Opt-in Telegram/garage/site adapters. OFF preserves all legacy payment rows and routes."""

import os, re, json, hashlib
from datetime import datetime, timezone
from bot.billing.transport import Transport
from bot.billing.models import BillingError
from bot.database.base import fetchrow, execute, transaction

PRODUCT_FLAGS = {
    "garage": "BOT_GLOBAL_GARAGE_ENABLED",
    "site": "BOT_GLOBAL_SITES_ENABLED",
    "site_standard": "BOT_GLOBAL_SITES_ENABLED",
    "site_plus": "BOT_GLOBAL_SITES_ENABLED",
    "seller_crm": "BOT_GLOBAL_CRM_ENABLED",
}


def enabled(product):
    return os.getenv(PRODUCT_FLAGS.get(product, "")) == "true"


def environment():
    env = os.environ["BOT_BILLING_ENVIRONMENT"]
    deployment = os.environ["BOT_BILLING_DEPLOYMENT"]
    if not (
        env == "sandbox"
        and deployment in {"local", "staging"}
        or env == "production"
        and deployment == "production"
    ):
        raise BillingError("Product Billing environment mismatch")
    return env


def client():
    try:
        from bot.billing.client import BillingClient

        return BillingClient(
            os.environ["BOT_BILLING_API_URL"],
            os.environ["BOT_BILLING_SERVICE_KEY"].encode(),
            "telegram",
            environment(),
        )
    except (KeyError, ImportError) as exc:
        raise BillingError(
            "Explicit product Billing configuration and optional SDK dependency required"
        ) from exc


def claims(b):
    return dict(principal_id=b["principal_id"], account_id=b["account_id"])


def canonical_order(order):
    return isinstance(order, str) and order.startswith(
        ("carpot-sandbox-", "carpot-production-")
    )


def sku_for(product, amount):
    if type(amount) is not int:
        raise BillingError("Server product amount required")
    if product == "garage":
        sku = {99: "garage.slots.1", 199: "garage.slots.5", 299: "garage.slots.10"}.get(
            amount
        )
    elif product in {"site", "site_standard"}:
        sku = "site.standard" if amount == 499 else None
    elif product == "seller_crm":
        sku = "seller_crm.standard" if amount == 99 else None
    else:
        sku = None
    if not sku:
        raise BillingError("Approved product quote and fulfillment terms required")
    return sku


async def create_checkout(seller_id, product, amount):
    sku = sku_for(product, amount)
    product = sku.split(".")[0]
    env = environment()
    api = client()
    seller = await fetchrow("SELECT id,telegram_id FROM sellers WHERE id=$1", seller_id)
    if not seller or not seller["telegram_id"]:
        raise BillingError("Verified seller ownership required")
    principal = "telegram:" + str(seller["telegram_id"])
    workspace = "seller:" + str(seller_id)
    b = await fetchrow(
        "SELECT * FROM global_billing_bindings WHERE seller_id=$1 AND product=$2 AND environment=$3",
        seller_id,
        product,
        env,
    )
    if not b:
        body = dict(workspace_id=workspace, product=product)
        b = await api.request(
            "POST",
            "/v1/bindings",
            dict(
                principal_id=principal,
                workspace_id=workspace,
                product=product,
                owner_verified=True,
            ),
            body,
        )
        await execute(
            "INSERT INTO global_billing_bindings VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING",
            seller_id,
            product,
            env,
            principal,
            b["account_id"],
            b["binding_id"],
        )
        b = await fetchrow(
            "SELECT * FROM global_billing_bindings WHERE seller_id=$1 AND product=$2 AND environment=$3",
            seller_id,
            product,
            env,
        )
    if b["principal_id"] != principal:
        raise BillingError("Seller ownership changed; binding review required")
    from uuid import uuid4

    invoice = await api.request(
        "POST",
        "/v1/invoices",
        claims(b),
        dict(
            binding_id=b["binding_id"], sku=sku, request_key="telegram:" + uuid4().hex
        ),
    )
    order = await api.request(
        "POST", "/v1/checkout", claims(b), dict(invoice_id=invoice["id"])
    )
    url = order.get("hosted_url")
    if not url or not url.startswith(api.url + "/pay/"):
        raise BillingError("Safe hosted checkout not configured")
    await execute(
        "INSERT INTO global_billing_orders VALUES ($1,$2) ON CONFLICT DO NOTHING",
        order["order_id"],
        b["binding_id"],
    )
    return dict(url=url, order_id=order["order_id"])


async def apply_projection(b, proof):
    env = environment()
    api = client()
    e = Transport(
        api.key, "billing-api", "telegram", "entitlements.write", environment=env
    ).verify(proof)
    p = e["payload"]
    if (
        (
            p.get("schema_version"),
            p.get("environment"),
            p.get("product"),
            p.get("workspace_id"),
            p.get("billing_account_id"),
        )
        != (2, env, b["product"], "seller:" + str(b["seller_id"]), b["account_id"])
        or p.get("activates_real_services") != (env == "production")
        or type(p.get("version")) is not int
        or p["version"] < 1
    ):
        raise BillingError("Product entitlement scope mismatch")
    intervals = p.get("intervals")
    if not isinstance(intervals, list) or len(intervals) > 1000:
        raise BillingError("Invalid product intervals")
    for i in intervals:
        if (
            i.get("kind") != "base"
            or not str(i.get("sku", "")).startswith(b["product"] + ".")
            or type(i.get("vehicle_capacity")) is not int
            or not 0 <= i["vehicle_capacity"] <= 1000
        ):
            raise BillingError("Invalid product interval")
        start, end = (
            datetime.fromisoformat(i[k]) for k in ("effective_from", "effective_until")
        )
        if not start.tzinfo or not end.tzinfo or end <= start:
            raise BillingError("Invalid product period")
    digest = hashlib.sha256(
        json.dumps(p, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    async with transaction() as c:
        await c.execute(
            "SELECT binding_id FROM global_billing_bindings WHERE binding_id=$1 FOR UPDATE",
            b["binding_id"],
        )
        old = await c.fetchrow(
            "SELECT * FROM global_billing_projections WHERE binding_id=$1",
            b["binding_id"],
        )
        if old and old["version"] == p["version"] and old["digest"] != digest:
            raise BillingError("Conflicting projection version")
        if not old or old["version"] < p["version"]:
            await c.execute(
                "INSERT INTO global_billing_projections(binding_id,version,event_id,digest,payload) VALUES ($1,$2,$3,$4,$5::jsonb) ON CONFLICT(binding_id) DO UPDATE SET version=EXCLUDED.version,event_id=EXCLUDED.event_id,digest=EXCLUDED.digest,payload=EXCLUDED.payload,updated_at=now()",
                b["binding_id"],
                p["version"],
                p["event_id"],
                digest,
                json.dumps(p),
            )
    # Always acknowledge only a committed version; stale full snapshots cannot replace newer rights.
    version = max(p["version"], old["version"] if old else 0)
    ack = Transport(
        api.key, "telegram", "billing-api", "entitlements.ack", environment=env
    ).sign(
        dict(
            event_id=p["event_id"],
            version=version,
            workspace_id=p["workspace_id"],
            billing_account_id=p["billing_account_id"],
        )
    )
    await api.request("POST", "/v1/entitlements/ack", claims(b), dict(proof=ack))


async def sync_binding(b):
    reply = await client().request(
        "GET", "/v1/entitlements/" + b["binding_id"], claims(b)
    )
    if reply.get("proof"):
        await apply_projection(b, reply["proof"])
        await fulfill_site(b)


async def forward_callback(data, signature, order):
    # Untrusted order is routing only. Core performs signature, environment and correlation checks.
    if not canonical_order(order):
        raise BillingError("Canonical namespace required")
    api = client()
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15, connect=3), follow_redirects=False
        ) as c:
            r = await c.post(
                api.url + "/v1/liqpay/callback",
                data={"data": data, "signature": signature},
            )
            if r.status_code != 200:
                raise BillingError("Canonical callback not accepted")
    except httpx.HTTPError as exc:
        raise BillingError("Canonical callback temporarily unavailable") from exc
    b = await fetchrow(
        "SELECT b.* FROM global_billing_bindings b JOIN global_billing_orders o ON o.binding_id=b.binding_id WHERE o.order_id=$1",
        order,
    )
    if b:
        await sync_binding(b)
    return {"ok": True, "canonical": True}


async def active_intervals(seller_id, product):
    if not enabled(product):
        return []
    env = environment()
    row = await fetchrow(
        "SELECT p.payload FROM global_billing_projections p JOIN global_billing_bindings b ON b.binding_id=p.binding_id WHERE b.seller_id=$1 AND b.product=$2 AND b.environment=$3",
        seller_id,
        product,
        env,
    )
    if not row:
        return []
    p = (
        json.loads(row["payload"])
        if isinstance(row["payload"], str)
        else row["payload"]
    )
    now = datetime.now(timezone.utc)
    return [
        i
        for i in p["intervals"]
        if datetime.fromisoformat(i["effective_from"])
        <= now
        < datetime.fromisoformat(i["effective_until"])
    ]


async def projected_crm(row):
    if not row or not enabled("seller_crm"):
        return row
    result = dict(row)
    result["crm_enabled"] = bool(result.get("crm_enabled")) or bool(
        await active_intervals(result["seller_id"], "seller_crm")
    )
    return result


async def projected_site(row):
    if not row or not enabled("site"):
        return row
    managed = await fetchrow(
        "SELECT f.site_id FROM global_billing_fulfillment f JOIN global_billing_bindings b ON b.binding_id=f.binding_id WHERE f.site_id=$1 AND b.environment=$2",
        row["id"],
        environment(),
    )
    if managed and not await active_intervals(row["seller_id"], "site"):
        return None
    return row


async def fulfill_site(b):
    if b["product"] != "site" or not await active_intervals(b["seller_id"], "site"):
        return
    from bot.services.site_config import (
        get_default_site_config,
        merge_with_default,
        apply_launch_defaults,
    )

    config = apply_launch_defaults(
        merge_with_default(get_default_site_config()), initial_creation=True
    )
    async with transaction() as c:
        await c.execute("SELECT id FROM sellers WHERE id=$1 FOR UPDATE", b["seller_id"])
        site = await c.fetchrow(
            "INSERT INTO seller_sites(seller_id,subdomain,config_draft,config_live,status) VALUES ($1,$2,$3::jsonb,$3::jsonb,'active') ON CONFLICT(seller_id) DO NOTHING RETURNING id",
            b["seller_id"],
            "user" + str(b["seller_id"]),
            json.dumps(config),
        )
        if site:
            await c.execute(
                "INSERT INTO global_billing_fulfillment(binding_id,site_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                b["binding_id"],
                site["id"],
            )
