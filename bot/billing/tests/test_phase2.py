from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4
from bot.billing.phase2 import migrate
from bot.billing.warehouse import anchored_month
from bot.billing.tests.conftest import opened, rows


def test_void_reissue_preserves_period_and_evidence(foundation):
    b, a, s, invoice, _ = foundation
    migrate(b.db)
    migrate(b.db)
    b.transition_invoice(a, invoice, "void")
    second = b.create_invoice(
        a,
        s,
        datetime(2026, 11, 12, tzinfo=timezone.utc),
        datetime(2026, 12, 12, tzinfo=timezone.utc),
        "replacement",
    )
    assert second != invoice and b.invoice(a, invoice)["status"] == "void"
    assert len(rows(b.db, "SELECT * FROM billing.periods")) == 1
    assert len(rows(b.db, "SELECT * FROM billing.invoice_lines")) == 2


def test_excess_payment_has_durable_evidence_without_second_access(foundation):
    b, *_ = foundation
    migrate(b.db)
    event = opened(foundation)
    assert b.receive_fixture(event) == "settled"
    extra = replace(event, event_id=str(uuid4()), transaction_id=str(uuid4()))
    assert b.receive_fixture(extra) == "reconciliation_required"
    assert b.receive_fixture(extra) == "duplicate"
    assert len(rows(b.db, "SELECT * FROM billing.reconciliation_cases")) == 1
    assert len(rows(b.db, "SELECT * FROM billing.settlements")) == 1
    assert len(rows(b.db, "SELECT * FROM billing.outbox")) == 1
    assert len(rows(b.db, "SELECT * FROM billing.webhook_inbox")) == 2


def test_calendar_anchor_returns_to_31_after_short_month():
    start = datetime(2027, 1, 31, tzinfo=timezone.utc)
    feb = anchored_month(start, anchor=31)
    assert feb.day == 28 and anchored_month(feb, anchor=31).day == 31
    leap = datetime(2028, 1, 31, tzinfo=timezone.utc)
    assert anchored_month(leap, anchor=31).day == 29


def test_invoice_calendar_anchor_is_persisted(foundation):
    from bot.billing.models import VerifiedBinding

    b, a, *_ = foundation
    migrate(b.db)
    binding = b.bind(
        a, VerifiedBinding("anchor-fixture", "warehouse", str(uuid4()), "fixture")
    )
    subscription = b.subscribe(a, binding, "warehouse.standard")
    jan = datetime(2027, 1, 31, tzinfo=timezone.utc)
    feb = datetime(2027, 2, 28, tzinfo=timezone.utc)
    mar = datetime(2027, 3, 31, tzinfo=timezone.utc)
    b.create_invoice(a, subscription, jan, feb, "anchor-first")
    b.create_invoice(a, subscription, feb, mar, "anchor-next")
    assert (
        rows(
            b.db,
            "SELECT calendar_anchor FROM billing.subscriptions WHERE id=%s",
            (subscription,),
        )[0]["calendar_anchor"]
        == 31
    )


def test_warehouse_bridge_reuses_canonical_phase1_company_binding(foundation):
    from bot.billing.warehouse import WarehouseBridge, migrate_phase2

    b, a, s, i, p = foundation
    migrate_phase2(b.db)
    bridge = WarehouseBridge(b.db, b"local-test-canonical-binding-key-123456789")
    binding = rows(
        b.db,
        "SELECT workspace_id FROM billing.bindings WHERE account_id=%s",
        (a.account_id,),
    )[0]
    token = bridge.owner_transport.sign(
        dict(workspace_id=binding["workspace_id"], owner_id=a.principal_id)
    )
    assert bridge.bind(token) == a.account_id
    assert len(rows(b.db, "SELECT * FROM billing.accounts")) == 1
    assert len(rows(b.db, "SELECT * FROM billing.bindings")) == 1
