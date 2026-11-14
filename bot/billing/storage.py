"""Explicit operational storage. Never reads legacy DATABASE_URL or migrates at startup."""

from contextlib import contextmanager
import os
from pathlib import Path
import psycopg2
from psycopg2.extensions import parse_dsn
from psycopg2.extras import RealDictCursor
from .models import BillingError
from .db import validate_disposable_dsn


class OperationalDatabase:
    def __init__(self, dsn, *, environment, role="application", disposable=False):
        if environment not in {"sandbox", "production"} or role not in {
            "application",
            "migrator",
        }:
            raise BillingError("Explicit Billing environment and role required")
        if not dsn or any(
            os.getenv(k)
            for k in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGHOSTADDR")
        ):
            raise BillingError("Explicit unambiguous Billing DSN required")
        p = parse_dsn(dsn)
        if not all(p.get(k) for k in ("host", "dbname", "user")) or any(
            p.get(k) for k in ("service", "options", "hostaddr")
        ):
            raise BillingError("Ambiguous Billing routing forbidden")
        if disposable:
            validate_disposable_dsn(dsn)
        elif p.get("sslmode") != "verify-full" or p["host"] in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise BillingError(
                "Operational DB requires explicit remote host and verified TLS"
            )
        self.dsn, self.environment, self.role, self.disposable = (
            dsn,
            environment,
            role,
            disposable,
        )

    @contextmanager
    def transaction(self):
        if any(
            os.getenv(k)
            for k in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGHOSTADDR")
        ):
            raise BillingError("Ambient operational DB routing forbidden")
        conn = psycopg2.connect(
            self.dsn,
            connect_timeout=5,
            cursor_factory=RealDictCursor,
            options="-c statement_timeout=15000 -c lock_timeout=5000",
        )
        try:
            with conn:
                with conn.cursor() as c:
                    c.execute(
                        "SELECT to_regclass('billing.operational_identity') AS relation"
                    )
                    if c.fetchone()["relation"]:
                        c.execute(
                            "SELECT environment FROM billing.operational_identity WHERE singleton=true"
                        )
                        identity = c.fetchone()
                        if not identity or identity["environment"] != self.environment:
                            raise BillingError("Billing database environment mismatch")
                    elif self.role != "migrator":
                        raise BillingError("Explicit operational migration required")
                    yield c
        finally:
            conn.close()

    def migrate(self):
        if self.role != "migrator":
            raise BillingError("Application credentials cannot run migrations")
        from .db import migrate_foundation

        migrate_foundation(self)

    def rollback(self):
        raise BillingError("Financial history is forward-only; disable routing instead")


def migrate_operational(db):
    if type(db) is not OperationalDatabase or db.role != "migrator":
        raise BillingError("Explicit operational migrator required")
    with db.transaction() as c:
        c.execute("SELECT to_regclass('billing.operational_identity') AS identity")
        established = bool(c.fetchone()["identity"])
        if not established:
            c.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' LIMIT 1")
            if c.fetchone():
                raise BillingError(
                    "Separate Billing database required; legacy/product DB adoption forbidden"
                )
            if db.environment == "production":
                for table in ("intents", "warehouse_trials"):
                    c.execute(
                        "SELECT to_regclass(%s) AS relation", ("billing." + table,)
                    )
                    if c.fetchone()["relation"]:
                        c.execute("SELECT 1 FROM billing." + table + " LIMIT 1")
                        if c.fetchone():
                            raise BillingError(
                                "Test financial/trial evidence cannot be adopted into production"
                            )
    from .phase2 import migrate
    from .warehouse import migrate_phase2

    migrate(db)
    migrate_phase2(db)
    with db.transaction() as c:
        c.execute("SELECT pg_advisory_xact_lock(48151901)")
        c.execute("SELECT version FROM billing.schema_migrations WHERE version=4")
        if c.fetchone():
            return
        c.execute(
            (Path(__file__).parent / "migrations/004_operational.sql").read_text()
        )
        c.execute(
            "INSERT INTO billing.operational_identity(singleton,environment) VALUES (true,%s)",
            (db.environment,),
        )
        c.execute("INSERT INTO billing.schema_migrations(version) VALUES (4)")


def migrate_all(db):
    """Operator CLI only. Runtime never calls this function."""
    migrate_operational(db)
    for path in sorted(
        (Path(__file__).parent / "migrations").glob("[0-9][0-9][0-9]_*.sql")
    ):
        version = int(path.name[:3])
        if version < 5:
            continue
        with db.transaction() as c:
            c.execute("SELECT pg_advisory_xact_lock(48151901)")
            c.execute(
                "SELECT version FROM billing.schema_migrations WHERE version=%s",
                (version,),
            )
            if c.fetchone():
                continue
            c.execute(path.read_text())
            c.execute(
                "INSERT INTO billing.schema_migrations(version) VALUES (%s)", (version,)
            )
