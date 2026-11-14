"""Separate ASGI service. Explicit environment, DSN and peer authentication; flags OFF."""

import os, json, time, threading, hashlib
from datetime import datetime, timezone
from urllib.parse import parse_qsl
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from .models import Actor, Permission, BillingError, Conflict, Forbidden
from .storage import OperationalDatabase, migrate_operational
from .global_core import GlobalBilling
from .liqpay_provider import ProviderProfile, LiqPayProvider
from .payments import Payments
from .transport import Transport


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Purchase(Command):
    binding_id: str = Field(min_length=1, max_length=160)
    sku: str = Field(min_length=1, max_length=100)
    request_key: str = Field(min_length=1, max_length=160)
    quantity: int = Field(default=1, strict=True, ge=1, le=1000)


class Checkout(Command):
    invoice_id: str = Field(min_length=1, max_length=160)


class Binding(Command):
    workspace_id: str = Field(min_length=1, max_length=160)
    product: str = Field(min_length=1, max_length=80)
    account_id: str | None = None


class Window:
    def __init__(self):
        self.lock = threading.Lock()
        self.count = 0
        self.start = 0

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            if now - self.start > 1:
                self.start = now
                self.count = 0
            self.count += 1
            if self.count > 100:
                raise HTTPException(429, "Забагато запитів; повторіть пізніше.")


def create_app(
    db=None, profile=None, *, peer_keys=None, checkout_enabled=None, provider=None
):
    if db is None:
        environment = os.environ["BILLING_ENVIRONMENT"]
        db = OperationalDatabase(
            os.environ["BILLING_OPERATIONAL_DSN"], environment=environment
        )
        profile = ProviderProfile(
            environment,
            os.environ["BILLING_LIQPAY_PUBLIC_KEY"],
            os.environ["BILLING_LIQPAY_PRIVATE_KEY"],
            os.environ["BILLING_RESULT_URL"],
            os.environ["BILLING_CALLBACK_URL"],
            protocol=os.getenv("BILLING_LIQPAY_PROFILE", "v7-sha3-256"),
            merchant_confirmed=os.getenv("BILLING_MERCHANT_CONFIRMED") == "true",
            live_enabled=os.getenv("BILLING_LIVE_ENABLED") == "true",
            network_enabled=os.getenv("BILLING_PROVIDER_NETWORK_ENABLED") == "true",
        )
        peer_keys = {
            name: value.encode()
            for name, value in json.loads(os.environ["BILLING_PEER_KEYS_JSON"]).items()
        }
        checkout_enabled = os.getenv("BILLING_CHECKOUT_ENABLED") == "true"
    if not peer_keys or any(len(k) < 32 for k in peer_keys.values()):
        raise BillingError("Explicit peer authentication keys required")
    core = GlobalBilling(db)
    payments = Payments(
        core,
        provider or LiqPayProvider(profile),
        checkout_enabled=checkout_enabled is True,
    )
    app = FastAPI(
        title="CarPot Billing", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.core, app.state.payments = core, payments
    limiter = Window()

    @app.middleware("http")
    async def bounded_body(request, call_next):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 70000:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        request._body = bytes(raw)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(BillingError)
    async def error(request, exc):
        status = (
            403
            if isinstance(exc, Forbidden)
            else 409
            if isinstance(exc, Conflict)
            else 400
        )
        return JSONResponse(
            {
                "detail": "Фінансову операцію не підтверджено. Перевірте стан або зверніться до підтримки."
            },
            status_code=status,
        )

    async def claims(request: Request):
        limiter.acquire()
        issuer = request.headers.get("X-CarPot-Peer", "")
        key = peer_keys.get(issuer)
        auth = request.headers.get("Authorization", "")
        if not key or not auth.startswith("Bearer "):
            raise HTTPException(401, "Авторизація потрібна")
        try:
            envelope = Transport(
                key,
                issuer,
                "billing-api",
                "billing.session",
                environment=db.environment,
            ).verify(auth[7:])
            payload = envelope["payload"]
            # A per-request nonce cannot be reused across different HTTP actions.
            if (
                payload.get("method") != request.method
                or payload.get("path") != request.url.path
                or payload.get("body_sha256")
                != hashlib.sha256(await request.body()).hexdigest()
            ):
                raise BillingError("Request scope mismatch")
            with db.transaction() as c:
                c.execute(
                    "INSERT INTO billing.api_receipts VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING nonce",
                    (
                        issuer,
                        envelope["jti"],
                        datetime.fromtimestamp(envelope["exp"], timezone.utc),
                    ),
                )
                if not c.fetchone():
                    raise BillingError("Transport replay")
            if not isinstance(payload.get("principal_id"), str):
                raise BillingError("Stable principal required")
            request.state.peer = issuer
            return payload
        except BillingError:
            raise HTTPException(401, "Недійсна авторизація") from None

    def actor(payload=Depends(claims)):
        if not isinstance(payload.get("account_id"), str):
            raise HTTPException(403, "Підтвердження компанії потрібне")
        return Actor(
            payload["principal_id"], payload["account_id"], frozenset(Permission)
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        with db.transaction() as c:
            c.execute("SELECT version FROM billing.schema_migrations WHERE version=4")
            if not c.fetchone():
                raise HTTPException(503, "Billing schema not ready")
        return dict(status="ready", environment=db.environment)

    @app.post("/v1/bindings")
    def bind(data: Binding, request: Request, payload=Depends(claims)):
        if (
            payload.get("owner_verified") is not True
            or payload.get("workspace_id") != data.workspace_id
            or payload.get("product") != data.product
        ):
            raise Forbidden("Trusted owner proof required")
        if data.account_id != payload.get("account_id"):
            raise Forbidden("Account linking proof mismatch")
        return core.bind_owner(
            data.workspace_id,
            payload["principal_id"],
            data.product,
            request.state.peer,
            account_id=data.account_id,
        )

    @app.get("/v1/catalogue")
    def catalogue(who=Depends(actor)):
        with db.transaction() as c:
            core.authorize(c, who, Permission.VIEW)
            c.execute(
                "SELECT * FROM billing.plan_versions ORDER BY product,sku,version DESC"
            )
            return {"items": [dict(r) for r in c.fetchall()]}

    @app.get("/v1/cabinet/{binding}")
    def cabinet(binding: str, who=Depends(actor)):
        result = core.cabinet(who, binding)
        result.update(
            checkout_available=payments.checkout_enabled,
            recurring_available=False,
            wallet_available=False,
        )
        return result

    @app.post("/v1/invoices")
    def invoice(data: Purchase, who=Depends(actor)):
        return core.purchase(
            who, data.binding_id, data.sku, data.request_key, quantity=data.quantity
        )

    @app.get("/v1/invoices/{invoice}")
    def get_invoice(invoice: str, who=Depends(actor)):
        with db.transaction() as c:
            core.authorize(c, who, Permission.VIEW)
            return core._invoice_view(c, who, invoice)

    @app.post("/v1/invoices/{invoice}/void")
    def void(invoice: str, who=Depends(actor)):
        core.transition_invoice(who, invoice, "void")
        return {"status": "void"}

    @app.post("/v1/checkout")
    def checkout(data: Checkout, who=Depends(actor)):
        return payments.checkout(who, data.invoice_id)

    @app.get("/v1/orders/{order}")
    def status(order: str, who=Depends(actor)):
        return payments.status(who, order)

    @app.post("/v1/orders/{order}/refresh")
    def refresh(order: str, who=Depends(actor)):
        return payments.reconcile(who, order)

    @app.post("/v1/liqpay/callback")
    async def callback(request: Request):
        limiter.acquire()
        if (
            request.headers.get("content-type", "").split(";")[0]
            != "application/x-www-form-urlencoded"
        ):
            raise HTTPException(415, "Form encoding required")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 70000:
                raise HTTPException(413, "Callback too large")
        try:
            pairs = parse_qsl(
                raw.decode("ascii"), strict_parsing=True, max_num_fields=2
            )
            if len(pairs) != 2 or {p[0] for p in pairs} != {"data", "signature"}:
                raise ValueError()
            value = dict(pairs)
        except (ValueError, UnicodeError):
            raise HTTPException(400, "Invalid callback") from None
        await run_in_threadpool(payments.callback, value["data"], value["signature"])
        return {"accepted": True}

    @app.get("/v1/admin/reconciliation")
    def reviews(request: Request, who=Depends(actor)):
        if request.state.peer not in set(
            os.getenv("BILLING_ADMIN_PEERS", "").split(",")
        ):
            raise Forbidden("Administrator peer required")
        with db.transaction() as c:
            core.authorize(c, who, Permission.MANAGE)
            c.execute(
                "SELECT id,invoice_id,reason,created_at FROM billing.reconciliation_cases WHERE account_id=%s ORDER BY created_at DESC LIMIT 100",
                (who.account_id,),
            )
            return {"items": [dict(r) for r in c.fetchall()]}

    return app


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["migrate"])
    args = p.parse_args()
    db = OperationalDatabase(
        os.environ["BILLING_MIGRATOR_DSN"],
        environment=os.environ["BILLING_ENVIRONMENT"],
        role="migrator",
    )
    migrate_operational(db)
    GlobalBilling(db).seed_catalogue()


if __name__ == "__main__":
    main()
