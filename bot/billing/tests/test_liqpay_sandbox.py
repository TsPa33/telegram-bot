"""Synthetic v7 contract and local sandbox evidence tests; no network/real keys."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import base64
import hashlib
import json
import subprocess

import pytest
import psycopg2

from bot.billing.liqpay import (
    CHECKOUT_URL, STATUS_URL, CheckoutTerms, SandboxCodec, SandboxContract,
)
from bot.billing.liqpay_sandbox import SandboxCheckout, migrate_sandbox
from bot.billing.models import BillingError, Conflict, Forbidden
from bot.billing.tests.conftest import rows

ORDER = "carpot-wh-sbx-" + "a" * 32


def contract():
    return SandboxContract("sandbox_fixture_public", "sandbox_fixture_private",
                           "https://warehouse.invalid/billing/result",
                           "https://finance.invalid/liqpay/callback")


def payload(order=ORDER, **patch):
    return {
        "version": 7, "public_key": contract().public_key, "action": "pay",
        "order_id": order, "amount": "1000.00", "currency": "UAH",
        "status": "success", "payment_id": 424242, **patch,
    }


def encode(codec, obj):
    data = base64.b64encode(json.dumps(obj, ensure_ascii=False,
                                       separators=(",", ":")).encode()).decode()
    return data, codec.signature(data)


def signed_raw(codec, raw):
    data = base64.b64encode(raw.encode()).decode()
    return data, codec.signature(data)


def local(foundation):
    b, actor, sub, invoice, _ = foundation
    migrate_sandbox(b.db)
    migrate_sandbox(b.db)
    b.transition_invoice(actor, invoice, "open")
    adapter = SandboxCheckout(b.db, contract(), enabled=True)
    return b, actor, sub, invoice, adapter


def test_checkout_and_status_are_server_signed_and_no_secret_exposed():
    codec = SandboxCodec(contract())
    terms = CheckoutTerms(ORDER, 100000)
    form = codec.checkout(terms)
    assert form["url"] == CHECKOUT_URL and form["method"] == "POST"
    obj = json.loads(base64.b64decode(form["data"]))
    assert obj == {
        "version": 7, "public_key": contract().public_key, "action": "pay",
        "amount": "1000.00", "currency": "UAH", "order_id": ORDER,
        "description": "CarPot Warehouse — тестова оплата", "language": "uk",
        "result_url": contract().result_url, "server_url": contract().server_url,
    }
    independent = subprocess.check_output(
        ["openssl", "dgst", "-sha3-256", "-binary"],
        input=(contract().private_key + form["data"] + contract().private_key).encode(),
    )
    assert form["signature"] == base64.b64encode(independent).decode()
    assert contract().private_key not in repr(contract())
    assert contract().private_key not in json.dumps(form)
    status = codec.status_request(terms)
    assert status["url"] == STATUS_URL and status["method"] == "POST"
    assert json.loads(base64.b64decode(status["data"])) == {
        "version": 7, "public_key": contract().public_key, "action": "status", "order_id": ORDER
    }


@pytest.mark.parametrize("changes", [
    {"public_key": "live_public"}, {"private_key": "live_private"},
    {"version": 3}, {"version": True}, {"result_url": "http://warehouse.invalid"},
    {"server_url": "https://u:p@finance.invalid/callback"},
    {"server_url": "https://finance.invalid:8443/callback"},
    {"server_url": "https://finance.invalid/callback#fragment"},
    {"server_url": "https://warehouse.invalid/billing/result"},
])
def test_no_live_legacy_or_untrusted_config(changes):
    with pytest.raises(BillingError):
        replace(contract(), **changes)


@pytest.mark.parametrize("changes", [
    {"amount_minor": True}, {"amount_minor": 0}, {"amount_minor": -1},
    {"amount_minor": 1.5}, {"amount_minor": 9_000_000_000_000_001},
    {"currency": "USD"}, {"order_id": "legacy-bot-order"},
])
def test_checkout_terms_are_strict(changes):
    with pytest.raises(BillingError):
        replace(CheckoutTerms(ORDER, 100000), **changes)


def test_tampered_signature_and_sha1_never_fallback():
    codec = SandboxCodec(contract())
    data, sign = encode(codec, payload())
    altered = "A" + sign[1:] if sign[0] != "A" else "B" + sign[1:]
    with pytest.raises(BillingError):
        codec.correlate(data, altered, CheckoutTerms(ORDER, 100000))
    legacy = base64.b64encode(hashlib.sha1((contract().private_key + data + contract().private_key).encode()).digest()).decode()
    with pytest.raises(BillingError):
        codec.verify(data, legacy)
    changed, _ = encode(codec, payload(amount="999.00"))
    with pytest.raises(BillingError):
        codec.verify(changed, sign)


@pytest.mark.parametrize("raw", [
    '{"version":7,"version":3}', '[]', '{"x":NaN}', '{"x":Infinity}',
    '{"x":1,"nested":{"a":1,"a":2}}', '{"x":',
])
def test_reject_signed_malformed_or_ambiguous_json(raw):
    codec = SandboxCodec(contract())
    with pytest.raises(BillingError):
        codec.verify(*signed_raw(codec, raw))


@pytest.mark.parametrize("patch", [
    {"public_key": "sandbox_other"}, {"version": 3}, {"version": "7"},
    {"action": "subscribe"}, {"action": "refund"},
    {"order_id": "carpot-wh-sbx-" + "b" * 32}, {"currency": "EUR"},
    {"amount": "1000.01"}, {"amount": True}, {"amount": "1000.001"},
    {"amount": "NaN"}, {"amount": None}, {"payment_id": None},
    {"payment_id": True}, {"payment_id": -1}, {"status": ""},
])
def test_signed_but_wrong_terms_are_rejected(patch):
    codec = SandboxCodec(contract())
    with pytest.raises(BillingError):
        codec.correlate(*encode(codec, payload(**patch)), CheckoutTerms(ORDER, 100000))


@pytest.mark.parametrize("status,classification", [
    ("success", "test_success"), ("sandbox", "test_success"),
    ("processing", "pending"), ("3ds_verify", "pending"),
    ("failure", "failed"), ("error", "failed"),
    ("subscribed", "review"), ("reversed", "review"),
    ("unsubscribed", "review"), ("future_state", "review"),
])
def test_classification_is_not_real_payment_authority(status, classification):
    codec = SandboxCodec(contract())
    e = codec.correlate(*encode(codec, payload(status=status)), CheckoutTerms(ORDER, 100000))
    assert e.classification == classification and e.environment == "sandbox"
    assert e.payment_id == "424242" and e.amount_minor == 100000


def test_decimal_json_number_correlates_without_float_rounding():
    codec = SandboxCodec(contract())
    obj = json.dumps(payload())
    data, sign = signed_raw(codec, obj.replace('"1000.00"', "1000.00"))
    assert codec.correlate(data, sign, CheckoutTerms(ORDER, 100000)).amount_minor == 100000


def test_local_order_idempotence_and_no_real_grant(foundation):
    b, actor, _, invoice, s = local(foundation)
    first = s.create(actor, invoice)
    assert first == s.create(actor, invoice)
    assert first["amount_minor"] == 100000 and not first["activates_real_services"]
    order = first["order_id"]
    assert s.status(actor, order)["status"] == "created"
    data, sig = encode(s.codec, payload(order))
    assert s.receive(data, sig) == "test_success"
    assert s.receive(data, sig) == "duplicate"
    assert s.status(actor, order)["status"] == "test_success"
    assert not s.status(actor, order)["activates_real_services"]
    assert b.invoice(actor, invoice)["status"] == "open"
    for table in ("settlements", "journal_entries", "outbox", "intents"):
        assert not rows(b.db, f"SELECT * FROM billing.{table}")
    assert len(rows(b.db, "SELECT * FROM billing.liqpay_sandbox_events")) == 1


def test_parallel_order_and_callback_replays(foundation):
    b, actor, _, invoice, s = local(foundation)
    with ThreadPoolExecutor(2) as pool:
        first, second = pool.map(lambda _: s.create(actor, invoice), range(2))
    assert first == second
    data, sig = encode(s.codec, payload(first["order_id"]))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: s.receive(data, sig), range(2)))
    assert sorted(results) == ["duplicate", "test_success"]
    assert len(rows(b.db, "SELECT * FROM billing.liqpay_sandbox_orders")) == 1
    assert len(rows(b.db, "SELECT * FROM billing.liqpay_sandbox_events")) == 1


def test_status_ordering_and_reconciliation(foundation):
    b, actor, _, invoice, s = local(foundation)
    order = s.create(actor, invoice)["order_id"]
    for status in ("processing", "failure", "success", "processing"):
        s.receive(*encode(s.codec, payload(order, status=status)))
    assert s.status(actor, order)["status"] == "test_success"
    assert s.receive(*encode(s.codec, payload(order, payment_id=424243))) == "review"
    assert s.status(actor, order)["status"] == "review"
    assert b.invoice(actor, invoice)["status"] == "open"


def test_cross_invoice_transaction_collision_never_confirms_second(foundation):
    b, actor, sub, invoice, s = local(foundation)
    first = s.create(actor, invoice)["order_id"]
    start = datetime(2026, 12, 12, tzinfo=timezone.utc)
    end = datetime(2027, 1, 12, tzinfo=timezone.utc)
    invoice2 = b.create_invoice(actor, sub, start, end, "next")
    b.transition_invoice(actor, invoice2, "open")
    second = s.create(actor, invoice2)["order_id"]
    assert s.receive(*encode(s.codec, payload(first))) == "test_success"
    assert s.receive(*encode(s.codec, payload(second))) == "review"
    assert s.status(actor, first)["status"] == "test_success"
    assert s.status(actor, second)["status"] == "review"
    assert not rows(b.db, "SELECT * FROM billing.settlements")


def test_tenant_permissions_open_invoice_and_explicit_enable(foundation):
    b, actor, _, invoice, _ = foundation
    migrate_sandbox(b.db)
    with pytest.raises(BillingError):
        SandboxCheckout(b.db, contract())
    s = SandboxCheckout(b.db, contract(), enabled=True)
    with pytest.raises(Conflict):
        s.create(actor, invoice)
    b.transition_invoice(actor, invoice, "open")
    order = s.create(actor, invoice)["order_id"]
    outsider = b.provision_fixture_account("outsider")
    with pytest.raises(Forbidden):
        s.create(outsider, invoice)
    with pytest.raises(Forbidden):
        s.status(outsider, order)
    limited = replace(actor, permissions=frozenset())
    with pytest.raises(Forbidden):
        s.create(limited, invoice)
    with pytest.raises(Forbidden):
        s.status(limited, order)
    other_contract = replace(contract(), public_key="sandbox_another")
    with pytest.raises(Conflict):
        SandboxCheckout(b.db, other_contract, enabled=True).create(actor, invoice)


def test_invalid_callback_is_not_persisted_and_history_immutable(foundation):
    b, actor, _, invoice, s = local(foundation)
    order = s.create(actor, invoice)["order_id"]
    with pytest.raises(BillingError):
        s.receive(*encode(s.codec, payload(order, amount="999.99")))
    with pytest.raises(BillingError):
        s.receive(*encode(s.codec, payload("carpot-wh-sbx-" + "b" * 32)))
    assert not rows(b.db, "SELECT * FROM billing.liqpay_sandbox_events")
    s.receive(*encode(s.codec, payload(order)))
    for table in ("liqpay_sandbox_orders", "liqpay_sandbox_events", "liqpay_sandbox_payment_ids"):
        with pytest.raises(psycopg2.Error):
            with b.db.transaction() as c:
                c.execute(f"DELETE FROM billing.{table}")
