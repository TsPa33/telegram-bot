"""Targeted sandbox ledger invariants and real canonical-settlement reward hooks."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import pytest
from bot.billing.tests.test_operational import operational, callback
from bot.billing.tests.conftest import rows
from bot.billing.models import Actor, Permission, BillingError, Conflict
from bot.billing.wallet import Wallet
from bot.billing.referrals import Referrals
from bot.billing.global_core import utcnow


def test_wallet_ledger_reservation_race_capture_refund_and_real_gates(operational):
    core, _, _, a, _, _ = operational
    w = Wallet(core, enabled=True)
    with pytest.raises(BillingError):
        Wallet(core).test_credit(a, 1000, "off")
    credit = w.test_credit(a, 1000, "topup")
    assert w.test_credit(a, 1000, "topup") == credit
    assert w.view(a)["balances"]["cash"]["available_minor"] == 1000

    def reserve(key):
        try:
            return w.reserve(a, 700, key)
        except Conflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        reservations = list(pool.map(reserve, ["r1", "r2"]))
    assert len([r for r in reservations if r]) == 1
    reservation = next(r for r in reservations if r)
    capture = w.finish(a, reservation, 500, "capture")
    w.finish(a, reservation, 200, "release", release=True)
    assert w.finish(a, reservation, 500, "capture") == capture
    with pytest.raises(Conflict):
        w.finish(a, reservation, 1, "overspend")
    w.refund(a, capture, 250, "refund")
    w.refund(a, capture, 250, "refund")
    with pytest.raises(Conflict):
        w.refund(a, capture, 251, "excess-refund")
    assert w.view(a)["balances"]["cash"] == dict(
        available_minor=750, reserved_minor=0, pending_minor=0
    )
    w.test_credit(a, 300, "promo", bucket="promo")
    assert w.view(a)["balances"]["promo"]["available_minor"] == 300
    w.reverse_credit(a, credit, 1000, "credit-reversal")
    assert w.view(a)["balances"]["cash"]["available_minor"] == -250
    with pytest.raises(Conflict):
        w.reserve(a, 1, "debt-spend")
    with pytest.raises(BillingError):
        w.payout(a, 1)
    assert not rows(core.db, "SELECT * FROM billing.settlements")
    assert all(
        r["total"] == 0
        for r in rows(
            core.db,
            "SELECT transaction_id,sum(amount_minor) AS total FROM billing.journal_entries GROUP BY transaction_id",
        )
    )


def test_first_base_reward_once_pending_available_partial_and_full_reversal(
    operational, monkeypatch
):
    core, payments, p, a, binding, invoice = operational
    monkeypatch.setenv("BILLING_REFERRALS_TEST_ENABLED", "true")
    referrals = Referrals(core, enabled=True)
    bound = core.bind_owner(
        "referrer-workspace", "different-owner", "warehouse", "warehouse"
    )
    referrer = Actor("different-owner", bound["account_id"], frozenset(Permission))
    code = referrals.code(referrer)
    with pytest.raises(BillingError):
        referrals.bind(referrer, code)
    assert referrals.bind(a, code)["referrer_account"] == referrer.account_id
    assert referrals.bind(a, code)["referrer_account"] == referrer.account_id
    w = Wallet(core, enabled=True)
    w.test_credit(a, 100000, "test-topup")
    assert referrals.history(referrer)["rewards"] == []
    order = payments.checkout(a, invoice)
    payments.callback(**callback(p, order))
    assert payments.callback(**callback(p, order)) == "duplicate"
    reward = referrals.history(referrer)["rewards"][0]
    assert reward["amount_minor"] == 20000 and reward["state"] == "pending"
    assert w.view(referrer)["balances"]["referral"]["pending_minor"] == 20000
    with pytest.raises(Conflict):
        referrals.release(reward["id"])
    p.profile = replace(p.profile, merchant_confirmed=True, reversals_confirmed=True)
    refund = callback(
        p,
        order,
        status="refund",
        refund_id="partial-reward-refund",
        refund_amount="250.00",
    )
    assert payments.verified_reversal(**refund) == "reversed"
    assert payments.verified_reversal(**refund) == "duplicate"
    assert w.view(referrer)["balances"]["referral"]["pending_minor"] == 15000
    assert referrals.release(reward["id"], now=utcnow() + timedelta(days=15))
    assert not referrals.release(reward["id"], now=utcnow() + timedelta(days=15))
    assert w.view(referrer)["balances"]["referral"]["available_minor"] == 15000
    final = callback(
        p,
        order,
        status="chargeback",
        refund_id="final-reward-chargeback",
        refund_amount="750.00",
    )
    assert payments.verified_reversal(**final) == "reversed"
    assert w.view(referrer)["balances"]["referral"] == dict(
        available_minor=0, pending_minor=0, reserved_minor=0
    )
    assert referrals.history(referrer)["rewards"][0]["state"] == "reversed"
    # A later paid renewal never mints another first-payment reward, including after refund.
    next_invoice = core.purchase(a, binding, "warehouse.standard", "renewal-referral")
    next_order = payments.checkout(a, next_invoice["id"])
    payments.callback(**callback(p, next_order, payment_id="second-base"))
    assert len(referrals.history(referrer)["rewards"]) == 1
