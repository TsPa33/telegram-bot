"""Synthetic two-DB Billing API -> Warehouse pipeline; no live network or keys."""

import os, json, hashlib
from contextlib import contextmanager
from uuid import uuid4
from dataclasses import replace
import pytest
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db import engine
from app.models.entitlements import EntitlementWorkspace, EntitlementReceipt
from app.services import global_billing as gateway, entitlements
from bot.billing.db import Database, validate_disposable_dsn
from bot.billing.storage import OperationalDatabase, migrate_all
from bot.billing.global_core import GlobalBilling
from bot.billing.liqpay_provider import ProviderProfile
from bot.billing.api import create_app
from bot.billing.transport import Transport

KEY = b"warehouse-global-synthetic-service-key-123456789"


@pytest.fixture
def global_pilot(logged, monkeypatch):
    dsn = os.environ.get("CARPOT_BILLING_TEST_DSN", "")
    validate_disposable_dsn(dsn)
    fixture = Database(dsn, enabled=True)
    with fixture.transaction() as c:
        c.execute("DROP SCHEMA IF EXISTS billing CASCADE")
    migration = OperationalDatabase(
        dsn, environment="sandbox", role="migrator", disposable=True
    )
    migrate_all(migration)
    financial = OperationalDatabase(dsn, environment="sandbox", disposable=True)
    core = GlobalBilling(financial)
    core.seed_catalogue()
    profile = ProviderProfile(
        "sandbox",
        "sandbox_public_warehouse",
        "sandbox_private_warehouse",
        "https://warehouse.example.test/settings?section=payments",
        "https://billing.example.test/v1/liqpay/callback",
    )
    application = create_app(
        financial, profile, peer_keys={"warehouse": KEY}, checkout_enabled=True
    )
    client = TestClient(application)
    client.__enter__()

    class LocalTransport:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def stream(self, method, url, **kwargs):
            assert url.startswith("https://billing.example.test/v1/")
            yield client.request(
                method, url.removeprefix("https://billing.example.test"), **kwargs
            )

    monkeypatch.setattr(gateway.httpx, "Client", LocalTransport)
    monkeypatch.setenv("WAREHOUSE_GLOBAL_BILLING_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_BILLING_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("WAREHOUSE_ENV", "local")
    monkeypatch.setenv("WAREHOUSE_BILLING_SERVICE_KEY", KEY.decode())
    monkeypatch.setenv("WAREHOUSE_BILLING_API_URL", "https://billing.example.test")
    monkeypatch.setenv("WAREHOUSE_GLOBAL_BILLING_MODE", "enforce")
    try:
        yield logged, application, core
    finally:
        client.__exit__(None, None, None)


def test_trial_checkout_callback_and_delivery_activate_only_the_bound_workspace(
    global_pilot,
):
    c, api, core = global_pilot
    assert c.get("/api/v1/billing/cabinet").json()["bound"] is False
    assert c.post("/api/v1/billing/bind").status_code == 200
    r = c.post("/api/v1/billing/trial", json={"plan": "standard"})
    assert r.status_code == 200, r.text
    deadline = r.json()["period_end"]
    assert r.json()["status"] == "TRIAL"
    assert (
        c.post("/api/v1/billing/trial", json={"plan": "premium"}).json()["period_end"]
        == deadline
    )
    invoice = c.post(
        "/api/v1/billing/invoices",
        json={"sku": "warehouse.standard", "request_key": str(uuid4())},
    )
    assert invoice.status_code == 200, invoice.text
    checkout = c.post(
        "/api/v1/billing/checkout", json={"invoice_id": invoice.json()["id"]}
    )
    assert checkout.status_code == 200, checkout.text
    order = checkout.json()
    assert order["amount_minor"] == 100000
    assert c.get("/api/v1/billing/orders/" + order["order_id"]).json()["paid"] is False
    provider = api.state.payments.provider
    signed = provider.sign(
        dict(
            version=7,
            public_key=provider.profile.public_key,
            order_id=order["order_id"],
            action="pay",
            amount="1000.00",
            currency="UAH",
            status="sandbox",
            payment_id="warehouse-synthetic-payment",
        )
    )
    assert api.state.payments.callback(**signed) == "settled"
    assert (
        c.get("/api/v1/billing/orders/" + order["order_id"]).json()[
            "activation_pending"
        ]
        is True
    )
    sync = c.post("/api/v1/billing/sync")
    assert sync.status_code == 200, sync.text
    assert sync.json()["status"] == "ACTIVE" and sync.json()["vehicle_capacity"] == 10
    assert c.post("/api/v1/billing/sync").json()["vehicle_capacity"] == 10
    assert (
        c.get("/api/v1/billing/orders/" + order["order_id"]).json()[
            "activation_pending"
        ]
        is False
    )
    assert (
        c.post(
            "/api/v1/billing/invoices",
            json={
                "sku": "warehouse.premium",
                "amount_minor": 1,
                "request_key": str(uuid4()),
            },
        ).status_code
        == 422
    )


def test_snapshot_environment_and_company_conflicts_do_not_write_projection(
    global_pilot,
):
    c, api, core = global_pilot
    c.post("/api/v1/billing/bind")
    c.post("/api/v1/billing/trial", json={"plan": "standard"})
    with core.db.transaction() as q:
        q.execute("SELECT payload FROM billing.outbox ORDER BY version DESC LIMIT 1")
        payload = dict(q.fetchone()["payload"])
    workspace = c.get("/api/v1/auth/me").json()["id"]
    with Session(engine()) as db:
        before = (
            db.get(EntitlementWorkspace, workspace).version,
            db.scalar(select(func.count()).select_from(EntitlementReceipt)),
        )
    for change in (
        {"environment": "production", "activates_real_services": True},
        {"billing_account_id": "another-company"},
        {"version": True},
        {"workspace_id": str(uuid4())},
    ):
        proof = Transport(
            KEY, "billing-api", "warehouse", "entitlements.write", environment="sandbox"
        ).sign({**payload, **change})
        r = c.post("/api/v1/billing/internal/entitlements", json={"proof": proof})
        assert r.status_code in (403, 409, 422), r.text
    with Session(engine()) as db:
        assert before == (
            db.get(EntitlementWorkspace, workspace).version,
            db.scalar(select(func.count()).select_from(EntitlementReceipt)),
        )


def test_staff_cannot_create_or_read_company_financial_orders(
    global_pilot, monkeypatch
):
    c, _, _ = global_pilot
    from test_team import employee, activate

    monkeypatch.setenv("WAREHOUSE_TEAM_CREATION_ENABLED", "true")
    c.post("/api/v1/billing/bind")
    c.post("/api/v1/billing/trial", json={"plan": "standard"})
    _, data = employee(c, ["inventory.view", "vehicles.view"])
    staff = activate(data)
    try:
        assert staff.get("/api/v1/billing/cabinet").json() == {
            "enabled": True,
            "can_manage": False,
        }
        assert (
            staff.post(
                "/api/v1/billing/invoices",
                json={"sku": "warehouse.standard", "request_key": str(uuid4())},
            ).status_code
            == 403
        )
        assert (
            staff.post(
                "/api/v1/billing/checkout", json={"invoice_id": str(uuid4())}
            ).status_code
            == 403
        )
    finally:
        staff.close()


def test_global_flags_off_preserve_legacy_disabled_checkout(logged, monkeypatch):
    monkeypatch.delenv("WAREHOUSE_GLOBAL_BILLING_ENABLED", raising=False)
    assert logged.get("/api/v1/billing/cabinet").json() == {"enabled": False}
    assert logged.post("/api/v1/billing/checkout").status_code == 503

    assert (
        logged.post("/api/v1/billing/checkout", json={"legacy": "ignored"}).status_code
        == 503
    )
