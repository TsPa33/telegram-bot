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


def test_referral_gateway_requires_flags_owner_and_valid_code(global_pilot, monkeypatch):
    c, _, core = global_pilot
    assert c.get("/api/v1/billing/referrals/status").json() == {"enabled": False}
    assert c.get("/api/v1/billing/referrals").json() == {"enabled": False}
    monkeypatch.setenv("WAREHOUSE_REFERRALS_TEST_ENABLED", "true")
    monkeypatch.setenv("BILLING_REFERRALS_TEST_ENABLED", "true")
    assert c.get("/api/v1/billing/referrals/status").json() == {"enabled": True}
    assert c.get("/api/v1/billing/referrals").json()["bound"] is False
    assert c.post("/api/v1/billing/bind").status_code == 200
    overview = c.get("/api/v1/billing/referrals")
    assert overview.status_code == 200, overview.text
    assert overview.json()["policy"]["rate_bps"] == 2000
    assert overview.json()["code"] is None
    code = c.post("/api/v1/billing/referrals/code").json()["code"]
    assert c.post("/api/v1/billing/referrals/code").json()["code"] == code
    assert c.post("/api/v1/billing/referrals/bind", json={"code": code}).status_code == 400
    assert c.post("/api/v1/billing/referrals/bind", json={"code": "bad"}).status_code == 422
    assert c.get("/api/v1/billing/referrals").json()["invited"] == 0
    from test_team import employee, activate
    monkeypatch.setenv("WAREHOUSE_TEAM_CREATION_ENABLED", "true")
    c.post("/api/v1/billing/trial", json={"plan": "standard"})
    _, data = employee(c, ["inventory.view", "vehicles.view"])
    staff = activate(data)
    try:
        assert staff.get("/api/v1/billing/referrals").status_code == 403
        assert staff.post("/api/v1/billing/referrals/code").status_code == 403
    finally:
        staff.close()


def _register_invited(client, code, suffix):
    r = client.post("/api/v1/auth/register", json={
        "name": "Invited " + suffix, "email": suffix + "@example.test",
        "password": "synthetic-password-123", "referral_code": code,
    })
    assert r.status_code == 201, r.text
    assert r.json()["billing_onboarding"] is True
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r.json()["user"]["id"]


def test_registration_automatically_attributes_only_new_owner(global_pilot, monkeypatch):
    from app.main import app
    c, _, core = global_pilot
    monkeypatch.setenv("WAREHOUSE_REFERRALS_TEST_ENABLED", "true")
    monkeypatch.setenv("BILLING_REFERRALS_TEST_ENABLED", "true")
    assert c.post("/api/v1/billing/bind").status_code == 200
    code = c.post("/api/v1/billing/referrals/code").json()["code"]
    with TestClient(app) as invited:
        workspace = _register_invited(invited, code, "automatic-invite")
        cabinet = invited.get("/api/v1/billing/cabinet").json()
        assert cabinet["bound"] is True and cabinet["referral_state"] == "accepted"
        assert invited.get("/api/v1/billing/referrals").json()["attributed"] is True
        assert c.get("/api/v1/billing/referrals").json()["invited"] == 1
        assert invited.post("/api/v1/billing/bind").status_code == 200
        # Repeat login and opening another URL cannot alter attribution.
        r = invited.post("/api/v1/auth/login", json={"email": "automatic-invite@example.test", "password": "synthetic-password-123"})
        assert r.status_code == 200
        invited.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        assert invited.get("/api/v1/billing/referrals").json()["attributed"] is True
        assert c.get("/api/v1/billing/referrals").json()["invited"] == 1
        with Session(engine()) as db:
            from app.models import Account
            row = db.get(Account, workspace)
            assert row.registration_referral_code == code
            assert row.registration_referral_state == "accepted"
    with TestClient(app) as invalid:
        unknown = "0" * 16 if code != "0" * 16 else "1" * 16
        _register_invited(invalid, unknown, "invalid-invite")
        cabinet = invalid.get("/api/v1/billing/cabinet").json()
        assert cabinet["bound"] and cabinet["referral_state"] == "invalid"
        assert invalid.get("/api/v1/billing/referrals").json()["attributed"] is False
        assert invalid.post("/api/v1/billing/invoices", json={"sku":"warehouse.standard","request_key":str(uuid4())}).status_code == 200


def test_registration_referral_intent_survives_outage_before_first_invoice(global_pilot, monkeypatch):
    from app.main import app
    c, _, core = global_pilot
    monkeypatch.setenv("WAREHOUSE_REFERRALS_TEST_ENABLED", "true")
    monkeypatch.setenv("BILLING_REFERRALS_TEST_ENABLED", "true")
    c.post("/api/v1/billing/bind")
    code = c.post("/api/v1/billing/referrals/code").json()["code"]
    original = gateway.request
    def offline(who, method, path, *args, **kwargs):
        if path == "/v1/referrals/bind":
            raise HTTPException(503, "temporary test outage")
        return original(who, method, path, *args, **kwargs)
    monkeypatch.setattr(gateway, "request", offline)
    with TestClient(app) as invited:
        workspace = _register_invited(invited, code, "outage-invite")
        assert invited.get("/api/v1/billing/cabinet").json()["referral_state"] == "pending"
        payload = {"sku":"warehouse.standard","request_key":str(uuid4())}
        assert invited.post("/api/v1/billing/invoices", json=payload).status_code == 503
        assert c.get("/api/v1/billing/referrals").json()["invited"] == 0
        monkeypatch.setattr(gateway, "request", original)
        result = invited.post("/api/v1/billing/invoices", json=payload)
        assert result.status_code == 200, result.text
        assert invited.get("/api/v1/billing/cabinet").json()["referral_state"] == "accepted"
        assert c.get("/api/v1/billing/referrals").json()["invited"] == 1
        assert invited.post("/api/v1/billing/invoices", json=payload).json()["id"] == result.json()["id"]
        assert c.get("/api/v1/billing/referrals").json()["invited"] == 1
