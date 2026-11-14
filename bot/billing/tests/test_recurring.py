"""Candidate recurring lifecycle; synthetic signed envelopes, no provider charges."""

from dataclasses import replace
from datetime import timedelta
import pytest
from bot.billing.tests.test_operational import operational, callback
from bot.billing.tests.conftest import rows
from bot.billing.models import BillingError, Conflict
from bot.billing.recurring import Recurring, CONSENT_VERSION
from bot.billing.global_core import utcnow


def test_recurring_consent_cycles_failure_and_cancel_preserve_paid_access(operational):
    core, payments, p, a, binding, invoice = operational
    recurring = Recurring(core, payments)
    with pytest.raises(BillingError):
        recurring.consent(
            a,
            binding,
            "warehouse.standard",
            "r1",
            accepted=True,
            version=CONSENT_VERSION,
        )
    p.profile = replace(p.profile, merchant_confirmed=True)
    recurring = Recurring(core, payments, enabled=True, contract_confirmed=True)
    with pytest.raises(BillingError):
        recurring.consent(
            a,
            binding,
            "warehouse.standard",
            "r1",
            accepted=False,
            version=CONSENT_VERSION,
        )
    order = payments.checkout(a, invoice)
    payments.callback(**callback(p, order))
    mandate = recurring.consent(
        a, binding, "warehouse.standard", "r1", accepted=True, version=CONSENT_VERSION
    )
    assert (
        recurring.consent(
            a,
            binding,
            "warehouse.standard",
            "r1",
            accepted=True,
            version=CONSENT_VERSION,
        )["id"]
        == mandate["id"]
    )
    registration = recurring.registration(a, mandate["id"])
    assert (
        p.decode_callback(registration["data"], registration["signature"])["action"]
        == "subscribe"
    )
    assert len(rows(core.db, "SELECT * FROM billing.settlements")) == 1
    period = rows(
        core.db,
        "SELECT p.* FROM billing.periods p JOIN billing.invoices i ON i.period_id=p.id WHERE i.id=%s",
        (invoice,),
    )[0]
    value = dict(
        version=7,
        public_key=p.profile.public_key,
        action="subscribe",
        currency="UAH",
        amount="1000.00",
        order_id=mandate["enrollment_order"],
        status="subscribed",
        subscription_id="subscription-synthetic",
        next_payment_at=period["ends_at"].isoformat(),
    )
    assert recurring.callback(**p.sign(value)) == "recorded_without_payment"
    assert len(rows(core.db, "SELECT * FROM billing.settlements")) == 1
    with pytest.raises(Conflict):
        core.purchase(a, binding, "warehouse.premium", "manual-double")
    cycle = recurring.prepare_cycle(a, mandate["id"])
    assert recurring.prepare_cycle(a, mandate["id"]) == cycle
    with pytest.raises(Conflict):
        payments.checkout(a, cycle["invoice_id"])
    cycle_order = dict(order_id=cycle["order_id"], amount_minor=100000)
    assert (
        payments.callback(
            **callback(
                p,
                cycle_order,
                status="failure",
                payment_id="failed-cycle",
                subscription_id="subscription-synthetic",
            )
        )
        == "failure"
    )
    assert len(rows(core.db, "SELECT * FROM billing.settlements")) == 1
    assert core.cabinet(a, binding)["subscription"]["recurring"]["last_failure_at"]
    with pytest.raises(BillingError):
        payments.callback(
            **callback(
                p,
                cycle_order,
                payment_id="cycle-wrong",
                subscription_id="another-subscription",
            )
        )
    assert (
        payments.callback(
            **callback(
                p,
                cycle_order,
                payment_id="cycle-good",
                subscription_id="subscription-synthetic",
            )
        )
        == "settled"
    )
    assert len(rows(core.db, "SELECT * FROM billing.settlements")) == 2
    assert recurring.cancel(a, mandate["id"])["state"] == "cancel_requested"
    with pytest.raises(Conflict):
        recurring.prepare_cycle(a, mandate["id"])
    assert (
        p.decode_callback(**recurring.cancellation_command(a, mandate["id"]))["action"]
        == "unsubscribe"
    )
    value["status"] = "unsubscribed"
    assert recurring.callback(**p.sign(value)) == "recorded_without_payment"
    assert recurring.callback(**p.sign(value)) == "duplicate"
    assert recurring.cancel(a, mandate["id"])["provider_confirmed"]
    cabinet = core.cabinet(a, binding)
    assert cabinet["subscription"]["auto_renew"] is False
    assert len(rows(core.db, "SELECT * FROM billing.settlements")) == 2
    assert len(rows(core.db, "SELECT * FROM billing.outbox")) == 2
