import logging
from pathlib import Path

from bot.database import pool as pool_module

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


async def run_sql_migrations() -> list[str]:
    if pool_module.pool is None:
        raise RuntimeError("Database pool is not initialized")

    applied: list[str] = []
    async with pool_module.pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )

        files = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
        for filename in files:
            exists = await conn.fetchval(
                "SELECT 1 FROM schema_migrations WHERE filename = $1 LIMIT 1",
                filename,
            )
            if exists:
                continue

            sql = (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations(filename) VALUES ($1)",
                    filename,
                )
            applied.append(filename)

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

    logger.info("DB migrations finished applied=%s", applied)
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
