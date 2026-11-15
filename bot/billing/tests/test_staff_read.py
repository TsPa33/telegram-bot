"""Disposable finance DB, real signed peer transport, no provider network."""

import hashlib
from fastapi.testclient import TestClient
from bot.billing.api import create_app
from bot.billing.models import Actor, Permission
from bot.billing.transport import Transport
from bot.billing.tests.test_operational import operational, callback, KEY
from bot.billing.tests.conftest import rows


STAFF_KEY = b"dedicated-control-center-read-key-1234567890"


def headers(
    binding,
    workspace="cc-workspace",
    environment="sandbox",
    scope="billing.staff.read",
    **changes,
):
    path = "/v1/staff/warehouse/" + binding
    p = dict(
        method="GET",
        path=path,
        body_sha256=hashlib.sha256(b"").hexdigest(),
        workspace_id=workspace,
        binding_id=binding,
        scope="warehouse.finance.read",
    )
    p.update(changes)
    token = Transport(
        STAFF_KEY, "control-center", "billing-api", scope, environment=environment
    ).sign(p)
    return {"Authorization": "Bearer " + token, "X-CarPot-Peer": "control-center"}


def test_staff_read_scope_replay_environment_and_no_mutation(operational, monkeypatch):
    core, payments, provider, *_ = operational
    core.seed_catalogue()
    bound = core.bind_owner("cc-workspace", "cc-owner", "warehouse", "warehouse")
    actor = Actor("cc-owner", bound["account_id"], frozenset(Permission))
    invoice = core.purchase(
        actor, bound["binding_id"], "warehouse.standard", "cc-first"
    )
    order = payments.checkout(actor, invoice["id"])
    signed = callback(provider, order)
    assert payments.callback(**signed) == "settled"
    assert payments.callback(**signed) == "duplicate"
    client = TestClient(
        create_app(
            db=core.db,
            peer_keys={"warehouse": KEY, "control-center": STAFF_KEY},
            profile=provider.profile,
            provider=provider,
        )
    )
    path = "/v1/staff/warehouse/" + bound["binding_id"]
    assert client.get(path, headers=headers(bound["binding_id"])).status_code == 404
    monkeypatch.setenv("BILLING_STAFF_READ_ENABLED", "true")
    before = {
        t: len(rows(core.db, "SELECT * FROM billing." + t))
        for t in [
            "accounts",
            "memberships",
            "invoices",
            "settlements",
            "journal_transactions",
            "outbox",
        ]
    }
    h = headers(bound["binding_id"])
    result = client.get(path, headers=h)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["environment"] == "sandbox" and len(data["payments"]) == 1
    assert data["payments"][0]["amount_minor"] == 100000
    assert data["totals_available"] is False
    assert client.get(path, headers=h).status_code == 401
    assert (
        client.get(
            path, headers=headers(bound["binding_id"], environment="production")
        ).status_code
        == 401
    )
    assert (
        client.get(
            path, headers=headers(bound["binding_id"], scope="billing.session")
        ).status_code
        == 401
    )
    assert (
        client.get(
            path, headers=headers(bound["binding_id"], method="POST")
        ).status_code
        == 401
    )
    assert (
        client.get(
            path, headers=headers(bound["binding_id"], body_sha256="bad")
        ).status_code
        == 401
    )
    assert (
        client.get(
            path, headers=headers(bound["binding_id"], workspace="someone-else")
        ).status_code
        == 403
    )
    assert client.post(path, headers=headers(bound["binding_id"])).status_code == 405
    after = {t: len(rows(core.db, "SELECT * FROM billing." + t)) for t in before}
    assert before == after


def test_non_warehouse_binding_rejected(operational, monkeypatch):
    core, payments, provider, *_ = operational
    bound = core.bind_owner("seller", "telegram-owner", "garage", "telegram")
    client = TestClient(
        create_app(
            db=core.db,
            peer_keys={"warehouse": KEY, "control-center": STAFF_KEY},
            profile=provider.profile,
            provider=provider,
        )
    )
    monkeypatch.setenv("BILLING_STAFF_READ_ENABLED", "true")
    result = client.get(
        "/v1/staff/warehouse/" + bound["binding_id"],
        headers=headers(bound["binding_id"], workspace="seller"),
    )
    assert result.status_code == 403
