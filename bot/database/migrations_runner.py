import logging
from pathlib import Path

from bot.database import pool as pool_module

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATION_LOCK_KEY = 2026052002
BASELINE_CUTOFF = "20260515"
BASELINE_CORE_TABLES = ("services", "sellers", "users", "seller_lead_actions")


async def _core_tables_exist(conn) -> bool:
    rows = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = ANY($1::text[])
        """,
        list(BASELINE_CORE_TABLES),
    )
    found = {row["table_name"] for row in rows}
    return all(name in found for name in BASELINE_CORE_TABLES)


def _is_historical_migration(filename: str) -> bool:
    return filename[:8].isdigit() and filename[:8] <= BASELINE_CUTOFF


async def run_sql_migrations() -> list[str]:
    if pool_module.pool is None:
        raise RuntimeError("Database pool is not initialized")

    applied: list[str] = []
    baselined: list[str] = []
    async with pool_module.pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_KEY)
        try:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )

            files = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
            migration_count = await conn.fetchval("SELECT COUNT(*)::int FROM schema_migrations")

            core_tables_exist = await _core_tables_exist(conn)

            if migration_count == 0 and core_tables_exist:
                historical = [name for name in files if _is_historical_migration(name)]
                if historical:
                    await conn.executemany(
                        "INSERT INTO schema_migrations(filename) VALUES ($1) ON CONFLICT (filename) DO NOTHING",
                        [(name,) for name in historical],
                    )
                    baselined.extend(historical)
                    logger.info(
                        "DB migration baseline detected: schema_migrations empty with existing core tables; baselined historical migrations=%s",
                        historical,
                    )

            for filename in files:
                exists = await conn.fetchval(
                    "SELECT 1 FROM schema_migrations WHERE filename = $1 LIMIT 1",
                    filename,
                )
                if exists:
                    logger.info("DB migration decision filename=%s decision=skip reason=already_applied", filename)
                    continue

                if core_tables_exist and _is_historical_migration(filename):
                    await conn.execute(
                        "INSERT INTO schema_migrations(filename) VALUES ($1) ON CONFLICT (filename) DO NOTHING",
                        filename,
                    )
                    baselined.append(filename)
                    logger.info(
                        "DB migration decision filename=%s decision=baseline reason=historical_migration_on_existing_schema",
                        filename,
                    )
                    continue

                logger.info("DB migration decision filename=%s decision=execute reason=pending", filename)
                sql = (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations(filename) VALUES ($1) ON CONFLICT (filename) DO NOTHING",
                        filename,
                    )
                applied.append(filename)
                logger.info("DB migration executed filename=%s", filename)

            row = await conn.fetchrow(
                """
                SELECT con.conname, pg_get_constraintdef(con.oid) AS constraint_def
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = 'seller_lead_actions'
                  AND con.contype = 'c'
                  AND pg_get_constraintdef(con.oid) ILIKE '%action IN (%'
                ORDER BY con.conname
                LIMIT 1
                """
            )
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_KEY)

    logger.info("DB migrations finished baselined=%s applied=%s", baselined, applied)
    if row:
        logger.info(
            "seller_lead_actions action constraint active name=%s def=%s",
            row["conname"],
            row["constraint_def"],
        )
    else:
        logger.warning("seller_lead_actions action constraint not found")
    return applied


async def get_seller_lead_action_constraints() -> list[dict]:
    if pool_module.pool is None:
        return []
    async with pool_module.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT con.conname, pg_get_constraintdef(con.oid) AS constraint_def
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = con.connamespace
            WHERE rel.relname = 'seller_lead_actions'
              AND nsp.nspname = current_schema()
              AND con.contype = 'c'
              AND pg_get_constraintdef(con.oid) ILIKE '%action IN (%'
            ORDER BY con.conname
            """
        )
    return [dict(row) for row in rows]
