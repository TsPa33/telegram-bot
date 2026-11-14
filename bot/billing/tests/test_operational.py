"""Real disposable PostgreSQL + synthetic provider evidence; NEVER a real LiqPay test."""

from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import hashlib, json
import httpx, pytest
from fastapi.testclient import TestClient
from bot.billing.storage import OperationalDatabase, migrate_all
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
    migrate_all(migration)
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


def test_addon_uses_current_paid_period_without_accumulating_monthly_credits(
    operational,
):
    core, payments, p, a, binding, invoice = operational
    order = payments.checkout(a, invoice)
    assert payments.callback(**callback(p, order)) == "settled"
    addon = core.purchase(a, binding, "warehouse.slots.5", "addon-request")
    assert 0 < addon["amount_minor"] <= 120000
    assert (
        core.purchase(a, binding, "warehouse.slots.5", "addon-request")["id"]
        == addon["id"]
    )
    add_order = payments.checkout(a, addon["id"])
    assert (
        payments.callback(**callback(p, add_order, payment_id="addon-payment"))
        == "settled"
    )
    snapshot = rows(
        core.db, "SELECT payload FROM billing.outbox ORDER BY version DESC LIMIT 1"
    )[0]["payload"]
    extra = next(i for i in snapshot["intervals"] if i["kind"] == "addon")
    assert extra["vehicle_capacity"] == 5 and extra["employee_seats"] == 0
    assert len([i for i in snapshot["intervals"] if i["kind"] == "base"]) == 1
    assert (
        extra["effective_until"]
        == next(i for i in snapshot["intervals"] if i["kind"] == "base")[
            "effective_until"
        ]
    )


def test_trial_race_and_plan_change_preserve_one_deadline(operational):
    core, _, _, a, binding, _ = operational
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(lambda plan: core.trial(a, binding, plan), ["standard", "premium"])
        )
    assert results[0]["deadline"] == results[1]["deadline"]
    assert len(rows(core.db, "SELECT * FROM billing.warehouse_trials")) == 1
    assert core.trial(a, binding, "standard")["deadline"] == results[0]["deadline"]


def test_delivery_ack_failure_and_replay_do_not_duplicate_rights(operational):
    from bot.billing.delivery import EntitlementDelivery

    core, payments, p, a, binding, invoice = operational
    core.bind_owner(
        "workspace-fixture",
        a.principal_id,
        "warehouse",
        "warehouse",
        account_id=a.account_id,
    )
    order = payments.checkout(a, invoice)
    payments.callback(**callback(p, order))
    received = set()
    attempts = []

    def consumer(request):
        token = json.loads(request.content)["proof"]
        payload = Transport(
            KEY, "billing-api", "warehouse", "entitlements.write", environment="sandbox"
        ).verify(token)["payload"]
        received.add(payload["event_id"])
        attempts.append(payload["version"])
        ack = Transport(
            KEY, "warehouse", "billing-api", "entitlements.ack", environment="sandbox"
        ).sign(
            {
                k: payload[k]
                for k in ("event_id", "workspace_id", "billing_account_id", "version")
            }
        )
        return httpx.Response(200, json={"ack": ack})

    delivery = EntitlementDelivery(
        core.db,
        {
            "warehouse": {
                "key": KEY,
                "url": "https://warehouse.example.test/api/v1/billing/internal/entitlements",
            }
        },
        network_enabled=True,
        transport=httpx.MockTransport(consumer),
    )
    latest = delivery.latest(core, a, binding)
    assert latest["proof"]
    assert delivery.run_once() == {"delivered": 1}
    assert delivery.run_once() == {"delivered": 0}
    assert len(received) == 1 and attempts == [1]
    assert payments.status(a, order["order_id"])["activation_pending"] is False
    with pytest.raises(BillingError):
        Transport(
            KEY,
            "billing-api",
            "warehouse",
            "entitlements.write",
            environment="production",
        ).verify(latest["proof"])


def test_refund_is_separate_immutable_journal_and_replay_safe(operational):
    core, payments, p, a, _, invoice = operational
    order = payments.checkout(a, invoice)
    payments.callback(**callback(p, order))
    payments.provider = LiqPayProvider(
        replace(p.profile, merchant_confirmed=True, reversals_confirmed=True)
    )
    refund = callback(
        p, order, status="reversed", refund_id="refund-one", refund_amount="1000.00"
    )
    assert payments.verified_reversal(**refund) == "reversed"
    assert payments.verified_reversal(**refund) == "duplicate"
    assert len(rows(core.db, "SELECT * FROM billing.settlements")) == 1
    assert len(rows(core.db, "SELECT * FROM billing.reversals")) == 1
    assert (
        rows(core.db, "SELECT sum(amount_minor) AS n FROM billing.journal_entries")[0][
            "n"
        ]
        == 0
    )
    last = rows(
        core.db, "SELECT payload FROM billing.outbox ORDER BY version DESC LIMIT 1"
    )[0]["payload"]
    assert last["intervals"] == []
    assert (
        rows(core.db, "SELECT status FROM billing.invoices WHERE id=%s", (invoice,))[0][
            "status"
        ]
        == "paid"
    )


def test_production_adoption_rejects_fixture_money_history(foundation):
    b, a, s, i, _ = foundation
    from bot.billing.tests.conftest import opened

    event = opened(foundation)
    b.receive_fixture(event)
    db = OperationalDatabase(
        b.db.dsn, environment="production", role="migrator", disposable=True
    )
    with pytest.raises(BillingError):
        migrate_all(db)


def test_product_terms_and_canonical_settlement(operational):
    core, payments, p, _, _, _ = operational
    core.seed_catalogue()
    from bot.billing.products import PRODUCTS
    from datetime import datetime, timezone

    for number, (sku, (product, amount, capacity, cadence)) in enumerate(
        PRODUCTS.items()
    ):
        bound = core.bind_owner(
            "seller:" + str(number), "telegram:" + str(number), product, "telegram"
        )
        a = Actor("telegram:" + str(number), bound["account_id"], frozenset(Permission))
        invoice = core.purchase(
            a,
            bound["binding_id"],
            sku,
            "product-1",
            now=datetime(2026, 11, 14, tzinfo=timezone.utc),
        )
        assert invoice["amount_minor"] == amount
        assert (invoice["ends_at"] - invoice["starts_at"]).days == (
            365 if cadence == "year" else 30
        )
        order = payments.checkout(a, invoice["id"])
        assert (
            payments.callback(**callback(p, order, payment_id="product-" + str(number)))
            == "settled"
        )
        snapshot = rows(
            core.db,
            "SELECT payload FROM billing.outbox WHERE account_id=%s",
            (a.account_id,),
        )[0]["payload"]
        assert snapshot["product"] == product and len(snapshot["intervals"]) == 1
        assert snapshot["intervals"][0]["vehicle_capacity"] == capacity
        next_invoice = core.purchase(a, bound["binding_id"], sku, "product-2")
        assert next_invoice["starts_at"] == invoice["ends_at"]


def test_hosted_capability_and_product_sdk(operational, monkeypatch):
    import asyncio
    from bot.billing.public_checkout import HostedLinks
    from bot.billing.client import BillingClient

    core, payments, p, a, _, invoice = operational
    monkeypatch.setenv("BILLING_PUBLIC_ORIGIN", "https://billing.example.test")
    monkeypatch.setenv(
        "BILLING_PUBLIC_LINK_KEY", "synthetic-only-public-link-key-123456789"
    )
    app = create_app(
        core.db, p.profile, peer_keys={"warehouse": KEY}, checkout_enabled=True
    )
    order = app.state.payments.checkout(a, invoice)
    token = order["hosted_url"].split("/pay/")[1]
    with TestClient(app) as c:
        page = c.get("/pay/" + token)
        assert page.status_code == 200 and 'method="post"' in page.text
        assert p.profile.private_key not in page.text and "cc-number" not in page.text
        assert "frame-ancestors" in page.headers["content-security-policy"]
        assert (
            c.get("/pay/" + token[:-1] + ("0" if token[-1] != "0" else "1")).status_code
            == 400
        )
    sdk = BillingClient(
        "https://billing.example.test",
        KEY,
        "warehouse",
        "sandbox",
        transport=httpx.ASGITransport(app=app),
    )
    reply = asyncio.run(
        sdk.request(
            "GET",
            "/v1/orders/" + order["order_id"],
            dict(principal_id=a.principal_id, account_id=a.account_id),
        )
    )
    assert reply["status"] == "pending"


def test_legacy_preview_cannot_mint_financial_evidence(operational):
    from bot.billing.products import LegacyMigration

    core, *_ = operational
    preview = LegacyMigration(core.db).preview(
        "telegram",
        [
            {"order_id": "old-uuid", "status": "success"},
            {"order_id": "old-uuid", "status": "success"},
        ],
    )
    assert (
        preview[0]["decision"] == "provider_verification_required"
        and preview[1]["duplicate"]
    )
    with pytest.raises(BillingError):
        LegacyMigration(core.db).map_verified(
            "telegram", "old-uuid", "missing", "missing", "missing"
        )
    assert not rows(core.db, "SELECT * FROM billing.legacy_mappings")


def test_application_role_runs_lifecycle_without_migration_or_history_privileges(
    operational, monkeypatch
):
    from pathlib import Path
    from contextlib import contextmanager
    from psycopg2 import sql, errors
    from bot.billing.delivery import EntitlementDelivery

    core, payments, p, _, _, _ = operational
    original = core.db.transaction
    role = "billing_test_" + uuid4().hex
    with original() as c:
        c.execute(
            sql.SQL(
                "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            ).format(sql.Identifier(role))
        )
        grants = (
            (Path(__file__).parents[1] / "deploy/grants.sql")
            .read_text()
            .replace(':"app_role"', sql.Identifier(role).as_string(c))
        )
        c.execute(grants)

    @contextmanager
    def scoped():
        with original() as c:
            c.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            yield c

    monkeypatch.setattr(core.db, "transaction", scoped)
    try:
        bound = core.bind_owner(
            "app-role-workspace", "app-role-owner", "warehouse", "warehouse"
        )
        actor = Actor("app-role-owner", bound["account_id"], frozenset(Permission))
        invoice = core.purchase(
            actor, bound["binding_id"], "warehouse.premium", "app-role-invoice"
        )
        order = payments.checkout(actor, invoice["id"])
        assert (
            payments.callback(**callback(p, order, payment_id="app-role-payment"))
            == "settled"
        )
        delivery = EntitlementDelivery(core.db, {"warehouse": {"key": KEY}})
        assert delivery.latest(core, actor, bound["binding_id"])["proof"]
        p.profile = replace(
            p.profile, merchant_confirmed=True, reversals_confirmed=True
        )
        assert (
            payments.verified_reversal(
                **callback(
                    p,
                    order,
                    status="refund",
                    refund_id="app-role-refund",
                    refund_amount="4500.00",
                    payment_id="app-role-payment",
                )
            )
            == "reversed"
        )
        for statement in (
            "DELETE FROM billing.settlements",
            "TRUNCATE billing.journal_entries",
            "CREATE TABLE billing.illegal(id int)",
            "UPDATE billing.schema_migrations SET version=99",
            "UPDATE billing.plan_versions SET amount_minor=1",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                with core.db.transaction() as c:
                    c.execute(statement)
        with pytest.raises(Exception, match="immutable"):
            with core.db.transaction() as c:
                c.execute("UPDATE billing.accounts SET id=id")
    finally:
        monkeypatch.setattr(core.db, "transaction", original)
        with original() as c:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_peer_product_allowlist_and_staff_permissions(operational):
    core, payments, p, a, binding, invoice = operational
    with core.db.transaction() as c:
        c.execute(
            "INSERT INTO billing.memberships VALUES (%s,%s,%s)",
            (a.account_id, "read-only-staff", [Permission.VIEW.value]),
        )
    staff = Actor("read-only-staff", a.account_id, frozenset({Permission.VIEW}))
    app = create_app(
        core.db, p.profile, peer_keys={"warehouse": KEY}, checkout_enabled=True
    )
    with TestClient(app) as c:
        path = "/v1/cabinet/" + binding
        assert c.get(path, headers=headers(staff, path)).json()["can_manage"] is False
        body = json.dumps({"invoice_id": invoice}).encode()
        assert (
            c.post(
                "/v1/checkout",
                content=body,
                headers={
                    **headers(staff, "/v1/checkout", "POST", body),
                    "Content-Type": "application/json",
                },
            ).status_code
            == 403
        )
        body = json.dumps(
            {"workspace_id": "another-product", "product": "garage"}
        ).encode()
        payload = dict(
            principal_id=a.principal_id,
            workspace_id="another-product",
            product="garage",
            owner_verified=True,
            method="POST",
            path="/v1/bindings",
            body_sha256=hashlib.sha256(body).hexdigest(),
        )
        proof = Transport(
            KEY, "warehouse", "billing-api", "billing.session", environment="sandbox"
        ).sign(payload)
        assert (
            c.post(
                "/v1/bindings",
                content=body,
                headers={
                    "X-CarPot-Peer": "warehouse",
                    "Authorization": "Bearer " + proof,
                    "Content-Type": "application/json",
                },
            ).status_code
            == 403
        )


def test_legacy_mapping_requires_original_provider_order_not_arbitrary_alias(
    operational,
):
    from bot.billing.products import LegacyMigration

    core, payments, p, a, binding, invoice = operational
    order = payments.checkout(a, invoice)
    event = callback(p, order)
    payments.callback(**event)
    settlement = rows(core.db, "SELECT * FROM billing.settlements")[0]
    digest = hashlib.sha256(event["data"].encode()).hexdigest()
    with pytest.raises(BillingError):
        LegacyMigration(core.db).map_verified(
            "telegram", "unrelated-legacy-order", invoice, settlement["id"], digest
        )
    assert not rows(core.db, "SELECT * FROM billing.legacy_mappings")
