import os
from uuid import uuid4
from datetime import datetime, timezone
import pytest
from bot.billing.db import Database, validate_disposable_dsn
from bot.billing.models import VerifiedBinding
from bot.billing.service import Billing
from bot.billing.projection import Projection
from bot.billing.providers import ProviderEvent


@pytest.fixture
def foundation():
    dsn = os.environ.get("CARPOT_BILLING_TEST_DSN", "")
    projection_dsn = os.environ.get("CARPOT_BILLING_PROJECTION_TEST_DSN", "")
    if not dsn or not projection_dsn:
        pytest.fail(
            "Explicit disposable finance and projection PostgreSQL DSNs required"
        )
    validate_disposable_dsn(dsn)
    validate_disposable_dsn(projection_dsn)
    if dsn == projection_dsn:
        pytest.fail("Separate finance and consumer databases required")
    db = Database(dsn, enabled=True)
    projection_db = Database(projection_dsn, enabled=True)
    # No legacy fixtures, migrations, truncation or production connection fallbacks.
    # Reset only these disposable schemas; DSNs are validated before connecting.
    with db.transaction() as cur:
        cur.execute("DROP SCHEMA IF EXISTS billing CASCADE")
    with projection_db.transaction() as cur:
        cur.execute("DROP SCHEMA IF EXISTS billing_projection CASCADE")
    db.migrate()
    projection = Projection(projection_db)
    projection.migrate()
    billing = Billing(db)
    billing.seed_catalogue()
    actor = billing.provision_fixture_account("owner-fixture")
    workspace = "workspace-fixture"
    binding = billing.bind(
        actor, VerifiedBinding(workspace, "warehouse", str(uuid4()), "fixture-verifier")
    )
    subscription = billing.subscribe(actor, binding, "warehouse.standard")
    projection.provision_fixture_binding(
        workspace, "warehouse", actor.account_id, subscription
    )
    start = datetime(2026, 11, 12, tzinfo=timezone.utc)
    end = datetime(2026, 12, 12, tzinfo=timezone.utc)
    invoice = billing.create_invoice(actor, subscription, start, end, "first-period")
    return billing, actor, subscription, invoice, projection


def opened(foundation):
    billing, actor, _, invoice, _ = foundation
    billing.transition_invoice(actor, invoice, "open")
    intent = billing.create_intent(actor, invoice)
    return ProviderEvent(
        "fixture",
        str(uuid4()),
        str(uuid4()),
        intent,
        100_000,
        "UAH",
        "disposable-fixture",
        "success",
        "test",
    )


def rows(db, query, params=()):
    with db.transaction() as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
