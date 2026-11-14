"""Explicitly local-only Phase 1 storage; no DATABASE_URL fallback or startup hook."""

from contextlib import contextmanager
from pathlib import Path
import os
import psycopg2
from psycopg2.extensions import parse_dsn
from psycopg2.extras import RealDictCursor
from .models import BillingError


def validate_disposable_dsn(dsn: str):
    options = parse_dsn(dsn)
    if (
        options.get("host") not in {"127.0.0.1", "localhost", "::1"}
        or not options.get("dbname", "").startswith("carpot_billing_")
        or not options.get("dbname", "").endswith("_test")
        or options.get("hostaddr")
        or options.get("service")
        or options.get("options")
    ):
        raise BillingError(
            "Only explicit loopback carpot_billing_*_test databases are allowed"
        )
    if any(
        os.getenv(k) for k in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGHOSTADDR")
    ):
        raise BillingError(
            "Ambient libpq routing/options are forbidden for fixture storage"
        )


class Database:
    def __init__(self, dsn: str, *, enabled: bool = False):
        if enabled is not True:
            raise BillingError("Billing foundation disabled by default")
        validate_disposable_dsn(dsn)
        self.dsn = dsn

    @contextmanager
    def transaction(self):
        # libpq may otherwise select an environment-provided address/service.
        validate_disposable_dsn(self.dsn)
        address = "::1" if parse_dsn(self.dsn)["host"] == "::1" else "127.0.0.1"
        conn = psycopg2.connect(
            self.dsn,
            hostaddr=address,
            options="",
            connect_timeout=5,
            cursor_factory=RealDictCursor,
        )
        try:
            with conn:
                with conn.cursor() as cursor:
                    yield cursor
        finally:
            conn.close()

    def migrate(self):
        migrate_foundation(self)

    def rollback(self):
        raise BillingError(
            "Destructive downgrade refused: preserve financial history; disable routing instead"
        )


def migrate_foundation(db):
    with db.transaction() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(48151901)")
        cur.execute("CREATE SCHEMA IF NOT EXISTS billing")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS billing.schema_migrations "
            "(version integer PRIMARY KEY, applied_at timestamptz DEFAULT now())"
        )
        cur.execute("SELECT version FROM billing.schema_migrations WHERE version=1")
        if cur.fetchone():
            return
        cur.execute(
            (Path(__file__).parent / "migrations/001_foundation.sql").read_text()
        )
        cur.execute("INSERT INTO billing.schema_migrations(version) VALUES (1)")
