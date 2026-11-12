from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import subprocess
import psycopg2
import pytest
from bot.billing.catalogue import CATALOGUE, money_minor, quote
from bot.billing.config import Flags, local_billing
from bot.billing.db import Database, validate_disposable_dsn
from bot.billing.models import (
    Actor,
    BillingError,
    Conflict,
    Forbidden,
    Permission,
    VerifiedBinding,
)
from bot.billing.projection import deliver_pending
from bot.billing.tests.conftest import opened, rows


@pytest.mark.parametrize(
    "value,expected", [("1000", 100000), ("0.01", 1), ("4500.00", 450000), ("0", 0)]
)
def test_money(value, expected):
    assert money_minor(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        1.1,
        "NaN",
        "Infinity",
        "-1",
        "0.001",
        "invalid",
        "999999999999999999999",
        "1000.000000000000000000000000000001",
        "1e-999999999",
    ],
)
def test_invalid_money(value):
    with pytest.raises(BillingError):
        money_minor(value)


def test_quote_proration_rounding_and_dst():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=30)
    assert (
        quote(
            CATALOGUE["warehouse.slots.5"], start, end, start + timedelta(days=15)
        ).payable_minor
        == 60000
    )
    tiny = replace(CATALOGUE["warehouse.slots.1"], amount_minor=1)
    assert (
        quote(tiny, start, end, start + timedelta(days=15)).payable_minor == 1
    )  # HALF_UP
    assert (
        quote(CATALOGUE["warehouse.standard"], start, end, start).payable_minor
        == 100000
    )
    with pytest.raises(BillingError):
        quote(tiny, start, end, end)
    with pytest.raises(BillingError):
        quote(tiny, start, end, start, True)
    with pytest.raises(BillingError):
        quote(tiny, start.replace(tzinfo=None), end, start)
    # Normalize offsets before subtraction; DST must not silently become wall-clock days.
    from zoneinfo import ZoneInfo

    a = datetime(2026, 10, 24, tzinfo=ZoneInfo("Europe/Kyiv"))
    b = datetime(2026, 10, 26, tzinfo=ZoneInfo("Europe/Kyiv"))
    mid = datetime(2026, 10, 25, tzinfo=ZoneInfo("Europe/Kyiv"))
    assert quote(CATALOGUE["warehouse.standard"], a, b, mid).payable_minor == 51020


@pytest.mark.parametrize(
    "dsn",
    [
        "host=postgres.railway.internal dbname=carpot_billing_a_test",
        "host=127.0.0.1 dbname=production",
        "host=127.0.0.1 dbname=warehouse_test",
        "host=127.0.0.1 dbname=carpot_billing_a_test hostaddr=1.2.3.4",
        "service=production host=127.0.0.1 dbname=carpot_billing_a_test",
    ],
)
def test_refuse_live_dsn(dsn):
    with pytest.raises(BillingError):
        validate_disposable_dsn(dsn)


def test_disabled_flags_and_ambient_routing(monkeypatch):
    for key in ("CARPOT_BILLING_FOUNDATION_ENABLED", "CARPOT_BILLING_FIXTURE_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    assert Flags.from_environment() == Flags()
    with pytest.raises(BillingError):
        local_billing("")
    with pytest.raises(BillingError):
        Database("")
    monkeypatch.setenv("PGSERVICE", "production")
    with pytest.raises(BillingError):
        validate_disposable_dsn("host=127.0.0.1 dbname=carpot_billing_a_test")


def test_migration_upgrade_idempotence_and_rollback(foundation):
    b, *_ = foundation
    b.db.migrate()
    assert (
        rows(b.db, "SELECT count(*) AS n FROM billing.schema_migrations")[0]["n"] == 1
    )
    with pytest.raises(BillingError):
        b.db.rollback()
    assert rows(b.db, "SELECT count(*) AS n FROM billing.invoices")[0]["n"] == 1


def test_invoice_lifecycle_and_idempotency(foundation):
    b, a, s, i, _ = foundation
    start = datetime(2026, 11, 12, tzinfo=timezone.utc)
    end = datetime(2026, 12, 12, tzinfo=timezone.utc)
    assert b.create_invoice(a, s, start, end, "first-period") == i
    with pytest.raises(Conflict):
        b.create_invoice(
            a, s, start + timedelta(days=1), end + timedelta(days=1), "first-period"
        )
    with pytest.raises(Conflict):
        b.create_invoice(a, s, start, end, "different-key")
    with pytest.raises(Conflict):
        b.create_intent(a, i)
    b.transition_invoice(a, i, "open")
    b.transition_invoice(a, i, "open")
    intent = b.create_intent(a, i)
    assert b.create_intent(a, i) == intent
    with pytest.raises(Conflict):
        b.transition_invoice(a, i, "void")
    with pytest.raises(BillingError):
        b.transition_invoice(a, i, "paid")


def test_void_draft(foundation):
    b, a, _, i, _ = foundation
    b.transition_invoice(a, i, "void")
    assert b.invoice(a, i)["status"] == "void"
    with pytest.raises(Conflict):
        b.transition_invoice(a, i, "open")


def test_base_period_cannot_buy_unlimited_access(foundation):
    from bot.billing.catalogue import monthly_end

    b, a, s, *_ = foundation
    start = datetime(2027, 1, 31, tzinfo=timezone.utc)
    assert monthly_end(start) == datetime(2027, 2, 28, tzinfo=timezone.utc)
    with pytest.raises(BillingError):
        b.create_invoice(
            a,
            s,
            start,
            datetime(2030, 1, 31, tzinfo=timezone.utc),
            "invalid-long-period",
        )


def test_balanced_immutable_settlement(foundation):
    b, a, _, i, _ = foundation
    e = opened(foundation)
    assert b.receive_fixture(e) == "settled"
    assert b.invoice(a, i)["status"] == "paid"
    assert rows(
        b.db,
        "SELECT sum(amount_minor) AS total,count(*) AS n FROM billing.journal_entries",
    )[0] == {"total": 0, "n": 2}
    for table in [
        "journal_entries",
        "journal_transactions",
        "settlements",
        "invoice_lines",
        "plan_versions",
    ]:
        with pytest.raises(psycopg2.Error):
            with b.db.transaction() as c:
                c.execute(f"DELETE FROM billing.{table}")
    journal = rows(b.db, "SELECT id FROM billing.journal_transactions")[0]["id"]
    with pytest.raises(psycopg2.Error):
        with b.db.transaction() as c:
            c.execute(
                "INSERT INTO billing.journal_entries VALUES (%s,%s,%s,'provider_clearing',1)",
                (str(uuid4()), journal, a.account_id),
            )


def test_unbalanced_or_empty_journal_cannot_commit(foundation):
    b, a, *_ = foundation
    for empty in (True, False):
        with pytest.raises(psycopg2.Error):
            with b.db.transaction() as c:
                journal = str(uuid4())
                c.execute(
                    "INSERT INTO billing.journal_transactions(id,account_id,external_key,currency) VALUES (%s,%s,%s,'UAH')",
                    (journal, a.account_id, journal),
                )
                if not empty:
                    c.execute(
                        "INSERT INTO billing.journal_entries VALUES (%s,%s,%s,'provider_clearing',10)",
                        (str(uuid4()), journal, a.account_id),
                    )
    assert not rows(b.db, "SELECT * FROM billing.journal_transactions")


def test_duplicate_and_parallel_settlement(foundation):
    b, *_ = foundation
    e = opened(foundation)
    events = [e, replace(e, event_id=str(uuid4()))]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(b.receive_fixture, events))
    assert sorted(results) == ["already_settled", "settled"]
    assert b.receive_fixture(e) == "duplicate"
    assert len(rows(b.db, "SELECT * FROM billing.settlements")) == 1
    assert len(rows(b.db, "SELECT * FROM billing.outbox")) == 1


def test_parallel_same_provider_event(foundation):
    b, *_ = foundation
    e = opened(foundation)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(b.receive_fixture, [e, e]))
    assert sorted(results) == ["duplicate", "settled"]


def test_late_out_of_order_events(foundation):
    b, *_ = foundation
    e = opened(foundation)
    assert (
        b.receive_fixture(replace(e, event_id=str(uuid4()), status="failure"))
        == "failure"
    )
    assert b.receive_fixture(e) == "settled"
    assert (
        b.receive_fixture(replace(e, event_id=str(uuid4()), status="pending"))
        == "already_settled"
    )
    assert (
        b.receive_fixture(replace(e, event_id=str(uuid4()), status="failure"))
        == "already_settled"
    )
    assert rows(b.db, "SELECT status FROM billing.attempts")[0]["status"] == "confirmed"
    with pytest.raises(Conflict):
        b.receive_fixture(
            replace(e, event_id=str(uuid4()), transaction_id="another-charge")
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"amount_minor": 99999},
        {"currency": "USD"},
        {"merchant": "another"},
        {"environment": "sandbox"},
        {"provider": "liqpay"},
        {"status": "sandbox"},
        {"amount_minor": True},
    ],
)
def test_provider_mismatch_rejected(foundation, patch):
    b, *_ = foundation
    e = opened(foundation)
    with pytest.raises(BillingError):
        b.receive_fixture(replace(e, **patch))
    assert not rows(b.db, "SELECT * FROM billing.settlements")


def test_event_identity_collision(foundation):
    b, *_ = foundation
    e = opened(foundation)
    b.receive_fixture(e)
    with pytest.raises(Conflict):
        b.receive_fixture(replace(e, status="failure"))


def test_crash_inside_settlement_rolls_back_everything(foundation):
    b, *_ = foundation
    e = opened(foundation)
    with b.db.transaction() as c:
        c.execute(
            "CREATE FUNCTION billing.fixture_crash() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture crash'; END $$"
        )
        c.execute(
            "CREATE TRIGGER crash BEFORE INSERT ON billing.outbox FOR EACH ROW EXECUTE FUNCTION billing.fixture_crash()"
        )
    with pytest.raises(psycopg2.Error):
        b.receive_fixture(e)
    for table in [
        "settlements",
        "journal_entries",
        "journal_transactions",
        "webhook_inbox",
    ]:
        assert not rows(b.db, f"SELECT * FROM billing.{table}")
    with b.db.transaction() as c:
        c.execute("DROP TRIGGER crash ON billing.outbox")
    assert b.receive_fixture(e) == "settled"


def test_crash_after_payment_before_entitlement_and_replay(foundation):
    b, a, _, i, projection = foundation
    e = opened(foundation)
    b.receive_fixture(e)
    assert b.invoice(a, i)["status"] == "paid"
    assert not rows(projection.db, "SELECT * FROM billing_projection.snapshots")
    payload = rows(b.db, "SELECT payload FROM billing.outbox")[0]["payload"]
    assert payload["activates_real_services"] is False
    assert projection.apply(payload) == "applied"  # crash before finance ack
    assert deliver_pending(b.db, projection) == 1
    assert deliver_pending(b.db, projection) == 0
    assert projection.apply(payload) == "duplicate"
    assert len(rows(projection.db, "SELECT * FROM billing_projection.snapshots")) == 1


def test_projection_ordering_and_binding(foundation):
    b, a, _, _, p = foundation
    b.receive_fixture(opened(foundation))
    payload = rows(b.db, "SELECT payload FROM billing.outbox")[0]["payload"]
    newer = {**payload, "version": 2, "event_id": str(uuid4())}
    assert p.apply(newer) == "applied"
    assert p.apply(payload) == "stale"
    with pytest.raises(Conflict):
        p.apply({**newer, "event_id": str(uuid4())})
    with pytest.raises(Forbidden):
        p.apply(
            {**payload, "workspace_id": "foreign-workspace", "event_id": str(uuid4())}
        )
    with pytest.raises(Forbidden):
        p.apply({**payload, "account_id": "foreign-account", "event_id": str(uuid4())})
    with pytest.raises(BillingError):
        p.apply({**payload, "activates_real_services": True})


def test_tenant_and_permission_isolation(foundation):
    b, a, s, i, _ = foundation
    other = b.provision_fixture_account("other-owner")
    with pytest.raises(Forbidden):
        b.invoice(other, i)
    with pytest.raises(Forbidden):
        b.create_intent(other, i)
    with pytest.raises(Forbidden):
        b.create_invoice(
            other,
            s,
            datetime(2027, 1, 1, tzinfo=timezone.utc),
            datetime(2027, 2, 1, tzinfo=timezone.utc),
            "foreign",
        )
    binding = rows(b.db, "SELECT id FROM billing.bindings")[0]["id"]
    with pytest.raises(Forbidden):
        b.subscribe(other, binding, "warehouse.standard")
    forged = Actor("employee", a.account_id, frozenset(Permission))
    with pytest.raises(Forbidden):
        b.invoice(forged, i)
    with b.db.transaction() as c:
        c.execute(
            "INSERT INTO billing.memberships VALUES (%s,%s,%s)",
            (a.account_id, "employee", ["billing.view"]),
        )
    assert b.invoice(forged, i)["id"] == i
    with pytest.raises(Forbidden):
        b.transition_invoice(forged, i, "open")
    limited = replace(a, permissions=frozenset())
    with pytest.raises(Forbidden):
        b.invoice(limited, i)
    personal = b.provision_fixture_account("employee-personal", kind="personal")
    with pytest.raises(Forbidden):
        b.bind(
            personal,
            VerifiedBinding("new", "warehouse", "evidence", "fixture-verifier"),
        )


def test_historical_price_and_issued_lines_immutable(foundation):
    b, a, _, i, _ = foundation
    b.transition_invoice(a, i, "open")
    with pytest.raises(psycopg2.Error):
        with b.db.transaction() as c:
            c.execute(
                "UPDATE billing.plan_versions SET amount_minor=1 WHERE sku='warehouse.standard'"
            )
    with pytest.raises(psycopg2.Error):
        with b.db.transaction() as c:
            c.execute("UPDATE billing.invoices SET amount_minor=1 WHERE id=%s", (i,))
    with b.db.transaction() as c:
        c.execute(
            "INSERT INTO billing.plan_versions VALUES ('warehouse.standard',2,'warehouse','base',110000,'UAH',10,5)"
        )
    assert b.invoice(a, i)["amount_minor"] == 100000
    b.seed_catalogue()


def test_parallel_invoice_creation(foundation):
    b, a, s, i, _ = foundation
    start = datetime(2026, 12, 12, tzinfo=timezone.utc)
    end = datetime(2027, 1, 12, tzinfo=timezone.utc)
    with ThreadPoolExecutor(2) as pool:
        invoices = list(
            pool.map(
                lambda _: b.create_invoice(a, s, start, end, "next-period"), range(2)
            )
        )
    assert invoices[0] == invoices[1]
    assert len(rows(b.db, "SELECT * FROM billing.invoices")) == 2


def test_late_period_payment_does_not_shorten_snapshot(foundation):
    b, a, s, first, p = foundation
    b.transition_invoice(a, first, "open")
    first_event = opened(foundation)
    start = datetime(2026, 12, 12, tzinfo=timezone.utc)
    end = datetime(2027, 1, 12, tzinfo=timezone.utc)
    second = b.create_invoice(a, s, start, end, "future-period")
    b.transition_invoice(a, second, "open")
    intent = b.create_intent(a, second)
    second_event = replace(
        first_event,
        intent_id=intent,
        event_id=str(uuid4()),
        transaction_id=str(uuid4()),
    )
    b.receive_fixture(second_event)
    b.receive_fixture(first_event)
    snapshots = rows(b.db, "SELECT payload FROM billing.outbox ORDER BY version")
    assert len(snapshots[0]["payload"]["paid_intervals"]) == 1
    assert len(snapshots[1]["payload"]["paid_intervals"]) == 2
    p.apply(snapshots[1]["payload"])
    assert p.apply(snapshots[0]["payload"]) == "stale"
    latest = rows(p.db, "SELECT payload FROM billing_projection.snapshots")[0][
        "payload"
    ]
    assert latest["paid_intervals"][-1]["end"] == end.isoformat()


def test_second_invoice_cannot_reuse_provider_transaction(foundation):
    b, a, s, _, _ = foundation
    e = opened(foundation)
    b.receive_fixture(e)
    i = b.create_invoice(
        a,
        s,
        datetime(2026, 12, 12, tzinfo=timezone.utc),
        datetime(2027, 1, 12, tzinfo=timezone.utc),
        "next",
    )
    b.transition_invoice(a, i, "open")
    intent = b.create_intent(a, i)
    with pytest.raises(psycopg2.Error):
        b.receive_fixture(replace(e, event_id=str(uuid4()), intent_id=intent))
    assert b.invoice(a, i)["status"] == "open"
    assert len(rows(b.db, "SELECT * FROM billing.settlements")) == 1


def test_projection_crash_before_ack_is_recoverable(foundation):
    b, *_, p = foundation
    b.receive_fixture(opened(foundation))
    with b.db.transaction() as c:
        c.execute(
            "CREATE FUNCTION billing.fail_ack() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'crash before ack'; END $$"
        )
        c.execute(
            "CREATE TRIGGER fail_ack BEFORE UPDATE ON billing.outbox FOR EACH ROW EXECUTE FUNCTION billing.fail_ack()"
        )
    with pytest.raises(psycopg2.Error):
        deliver_pending(b.db, p)
    assert len(rows(p.db, "SELECT * FROM billing_projection.snapshots")) == 1
    assert (
        rows(b.db, "SELECT delivered_at FROM billing.outbox")[0]["delivered_at"] is None
    )
    with b.db.transaction() as c:
        c.execute("DROP TRIGGER fail_ack ON billing.outbox")
    assert deliver_pending(b.db, p) == 1


def test_cross_company_foreign_keys_and_outbox_immutability(foundation):
    b, a, _, i, _ = foundation
    e = opened(foundation)
    b.receive_fixture(e)
    other = b.provision_fixture_account("other")
    with pytest.raises(psycopg2.Error):
        with b.db.transaction() as c:
            c.execute(
                "INSERT INTO billing.invoice_lines VALUES (%s,%s,%s,'warehouse.standard',1,1,100000,100000)",
                (str(uuid4()), other.account_id, i),
            )
    with pytest.raises(psycopg2.Error):
        with b.db.transaction() as c:
            c.execute("UPDATE billing.outbox SET payload='{}'")
    with pytest.raises(psycopg2.Error):
        with b.db.transaction() as c:
            c.execute("TRUNCATE billing.journal_entries")


def test_legacy_checkout_remains_fixture_only_without_network():
    # Execute only the original class AST, replacing its DB boundary with a stub.
    import ast, asyncio, base64, hashlib, json, logging

    source = Path("bot/services/liqpay_service.py").read_text()
    tree = ast.parse(source)
    node = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "LiqPayService"
    )

    async def create_payment(**kwargs):
        return {"order_id": kwargs["order_id"]}

    namespace = dict(
        base64=base64,
        json=json,
        hashlib=hashlib,
        uuid=__import__("uuid"),
        logger=logging.getLogger("legacy-fixture"),
        create_payment=create_payment,
        DESCRIPTIONS={},
    )
    exec(
        compile(
            ast.Module(body=[node], type_ignores=[]), "<legacy-class-fixture>", "exec"
        ),
        namespace,
    )
    result = asyncio.run(
        namespace["LiqPayService"]("fixture-public", "fixture-private").create_payment(
            99, "https://example.test/callback", 1, "unknown-fixture"
        )
    )
    from urllib.parse import urlsplit

    # Legacy concatenates unescaped base64; inspect raw query to preserve '+' bytes.
    # Its encoding problem belongs to the separately scoped provider migration.
    query = dict(
        part.split("=", 1) for part in urlsplit(result["url"]).query.split("&")
    )
    data = query["data"]
    payload = json.loads(base64.b64decode(data))
    assert (
        payload["action"] == "pay"
        and payload["sandbox"] == 1
        and payload["version"] == "3"
    )
    assert (
        query["signature"]
        == base64.b64encode(
            hashlib.sha1(
                ("fixture-private" + data + "fixture-private").encode()
            ).digest()
        ).decode()
    )


def test_legacy_and_warehouse_unchanged():
    root = Path(__file__).resolve().parents[3]
    # Strong scope regression: existing runtime trees must be byte-for-byte baseline.
    changed = subprocess.check_output(
        [
            "git",
            "diff",
            "160ffbeef61d80b174a82dca1bebef90c7f2e033",
            "--name-only",
            "--",
            "bot/api",
            "bot/services",
            "bot/database",
            "bot/handlers",
            "warehouse",
            "requirements.txt",
        ],
        cwd=root,
        text=True,
    )
    assert changed == ""
    # No startup registration or legacy provider coupling in the new module.
    for path in (root / "bot/billing").glob("*.py"):
        source = path.read_text()
        assert "from bot.config" not in source
        assert "from bot.database" not in source
        assert "from bot.api" not in source
