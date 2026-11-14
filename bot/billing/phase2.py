from pathlib import Path


def migrate(db):
    """Explicit local-only upgrade; not enabled by Phase 1 migrate/startup."""
    db.migrate()
    with db.transaction() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(48151901)")
        cur.execute("SELECT version FROM billing.schema_migrations WHERE version=2")
        if cur.fetchone():
            return
        cur.execute(
            (Path(__file__).parent / "migrations/002_reconciliation.sql").read_text()
        )
        cur.execute("INSERT INTO billing.schema_migrations(version) VALUES (2)")
