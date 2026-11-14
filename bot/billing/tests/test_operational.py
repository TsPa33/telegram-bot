"""Real disposable PostgreSQL + synthetic provider evidence; NEVER a real LiqPay test."""

from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import hashlib, json
import httpx, pytest
from fastapi.testclient import TestClient
from bot.billing.storage import OperationalDatabase, migrate_operational
from bot.billing.global_core import GlobalBilling, utcnow
from bot.billing.liqpay_provider import ProviderProfile, LiqPayProvider
from bot.billing.payments import Payments
from bot.billing.api import create_app
from bot.billing.models import Actor, Permission, BillingError, Forbidden, Conflict
from bot.billing.transport import Transport
from bot.billing.tests.conftest import rows

KEY = b"synthetic-operational-peer-authentication-key-12345"


@pytest.fixture
def operational(foundation):
    b, a, s, i, projection = foundation
    migration = OperationalDatabase(
        b.db.dsn, environment="sandbox", role="migrator", disposable=True
    )
    migrate_operational(migration)
    db = OperationalDatabase(b.db.dsn, environment="sandbox", disposable=True)
    core = GlobalBilling(db)
    profile = ProviderProfile(
        "sandbox",
        "sandbox_public_synthetic",
        "sandbox_private_synthetic",
        "https://example.test/settings?section=payments",
        "https://billing.example.test/v1/liqpay/callback",
    )
    provider = LiqPayProvider(profile, sleep=lambda _: None)
    payments = Payments(core, provider, checkout_enabled=True)
    binding = rows(
        db, "SELECT id FROM billing.bindings WHERE account_id=%s", (a.account_id,)
    )[0]["id"]
    core.transition_invoice(a, i, "open")
    return core, payments, provider, a, binding, i


def callback(provider, order, **changes):
    payload = dict(
        version=7,
        public_key=provider.profile.public_key,
        action="pay",
        order_id=order["order_id"],
        amount=str(order["amount_minor"] // 100)
        + "."
        + str(order["amount_minor"] % 100).zfill(2),
        currency="UAH",
        status="sandbox",
        payment_id="payment-one",
    )
    payload.update(changes)
    return provider.sign(payload)


def test_explicit_storage_and_environment_isolation(operational):
    core, *_ = operational
    with pytest.raises(BillingError):
        core.db.migrate()
    with pytest.raises(BillingError):
        OperationalDatabase(
            core.db.dsn, environment="production", disposable=True
        ).transaction().__enter__()
    with pytest.raises(BillingError):
        OperationalDatabase("", environment="sandbox")
    with pytest.raises(BillingError):
        GlobalBilling(core.db).provision_fixture_account("not-allowed")
    with pytest.raises(BillingError):
        ProviderProfile(
            "production",
            "live_public_synthetic",
            "live_private_synthetic",
            "https://x.test/result",
            "https://x.test/callback",
        )


def test_checkout_replay_and_parallel_verified_settlement(operational):
    core, payments, p, a, binding, invoice = operational
    order = payments.checkout(a, invoice)
    assert payments.checkout(a, invoice) == order
    signed = callback(p, order)
    with ThreadPoolExecutor(4) as pool:
        result = list(pool.map(lambda _: payments.callback(**signed), range(4)))
    assert result.count("settled") == 1 and result.count("duplicate") == 3
    assert rows(core.db, "SELECT count(*) AS n FROM billing.settlements")[0]["n"] == 1
    assert (
        rows(core.db, "SELECT sum(amount_minor) AS n FROM billing.journal_entries")[0][
            "n"
        ]
        == 0
    )
    payload = rows(core.db, "SELECT payload FROM billing.outbox")[0]["payload"]
    assert (
        payload["environment"] == "sandbox"
        and payload["activates_real_services"] is False
    )
    assert payload["intervals"][0]["vehicle_capacity"] == 10
    assert payments.status(a, order["order_id"])["paid"] is True
    assert (
        payments.callback(**callback(p, order, status="failure")) == "already_settled"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"amount": "999.99"},
        {"currency": "USD"},
        {"public_key": "sandbox_other_merchant"},
        {"order_id": "carpot-sandbox-" + "a" * 32},
        {"version": True},
        {"action": "subscribe"},
    ],
)
def test_tamper_never_posts_success(operational, change):
    core, payments, p, a, _, invoice = operational
    order = payments.checkout(a, invoice)
    with pytest.raises(BillingError):
        payments.callback(**callback(p, order, **change))
    assert not rows(core.db, "SELECT * FROM billing.settlements")
    assert not rows(core.db, "SELECT * FROM billing.journal_transactions")


def test_expired_and_second_payment_go_to_review_without_second_access(operational):
    core, payments, p, a, _, invoice = operational
    order = payments.checkout(a, invoice)
    assert payments.callback(**callback(p, order)) == "settled"
    assert payments.callback(**callback(p, order, payment_id="payment-two")) == "review"
    assert len(rows(core.db, "SELECT * FROM billing.settlements")) == 1
    assert len(rows(core.db, "SELECT * FROM billing.outbox")) == 1
    assert (
        rows(core.db, "SELECT sum(amount_minor) AS n FROM billing.journal_entries")[0][
            "n"
        ]
        == 0
    )
    assert (
        rows(core.db, "SELECT reason FROM billing.reconciliation_cases")[0]["reason"]
        == "excess_payment"
    )


def test_status_query_recovers_missing_callback(operational):
    core, payments, p, a, _, invoice = operational
    order = payments.checkout(a, invoice)
    raw = p.decode_callback(**callback(p, order))
    calls = []

    def provider(request):
        calls.append(request)
        assert request.url == httpx.URL("https://www.liqpay.ua/api/request")
        return httpx.Response(200, json=raw)

    payments.provider = LiqPayProvider(
        replace(p.profile, merchant_confirmed=True, network_enabled=True),
        transport=httpx.MockTransport(provider),
        sleep=lambda _: None,
    )
    assert payments.reconcile(a, order["order_id"])["paid"]
    assert len(calls) == 1
    assert payments.reconcile(a, order["order_id"])["paid"]
    assert len(rows(core.db, "SELECT * FROM billing.settlements")) == 1


def test_signed_unknown_and_invalid_signature(operational):
    core, payments, p, a, _, invoice = operational
    order = payments.checkout(a, invoice)
    signed = callback(p, order)
    with pytest.raises(BillingError):
        payments.callback(signed["data"], "x" * 44)
    assert payments.callback(**callback(p, order, status="subscribed")) == "review"
    assert not rows(core.db, "SELECT * FROM billing.settlements")


def headers(actor, path, method="GET", body=b""):
    payload = dict(
        account_id=actor.account_id,
        principal_id=actor.principal_id,
        method=method,
        path=path,
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    return {
        "X-CarPot-Peer": "warehouse",
        "Authorization": "Bearer "
        + Transport(
            KEY, "warehouse", "billing-api", "billing.session", environment="sandbox"
        ).sign(payload),
    }


def test_http_authorization_tenant_body_integrity_and_nonce(operational):
    core, payments, p, a, binding, invoice = operational
    app = create_app(
        core.db, p.profile, peer_keys={"warehouse": KEY}, checkout_enabled=True
    )
    with TestClient(app) as client:
        path = "/v1/cabinet/" + binding
        proof = headers(a, path)
        assert client.get(path, headers=proof).status_code == 200
        assert client.get(path, headers=proof).status_code == 401
        other = Actor(a.principal_id, "another-company", a.permissions)
        assert client.get(path, headers=headers(other, path)).status_code == 403
        body = json.dumps({"invoice_id": invoice}).encode()
        proof = headers(a, "/v1/checkout", "POST", body)
        assert (
            client.post(
                "/v1/checkout",
                content=body,
                headers={**proof, "Content-Type": "application/json"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/v1/checkout",
                content=b'{"invoice_id":"other"}',
                headers={
                    **headers(a, "/v1/checkout", "POST", body),
                    "Content-Type": "application/json",
                },
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/v1/liqpay/callback",
                content=b"x" * 70001,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ).status_code
            == 413
        )
