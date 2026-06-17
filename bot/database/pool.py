import asyncio
import logging
import os

import asyncpg

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None


def _database_ssl_mode(database_url: str):
    ssl_env = (os.getenv("DATABASE_SSL") or os.getenv("PGSSLMODE") or "").lower()
    url_lower = database_url.lower()
    if ssl_env in {"1", "true", "require", "required"} or "sslmode=require" in url_lower:
        return True
    if ssl_env in {"0", "false", "disable", "disabled"} or "sslmode=disable" in url_lower:
        return False
    return None


async def init_pool(max_attempts: int = 5, retry_delay_seconds: float = 4.0):
    global pool

    if pool is not None:
        return pool

    database_url = os.getenv("DATABASE_URL")
    logger.info("DATABASE_URL present: %s", "yes" if database_url else "no")
    if not database_url:
        logger.error("DATABASE_URL is missing; database pool cannot be initialized")
        raise RuntimeError("DATABASE_URL is not set")

    ssl_mode = _database_ssl_mode(database_url)
    logger.info(
        "Attempting DB pool init max_attempts=%s retry_delay_seconds=%s ssl=%s",
        max_attempts,
        retry_delay_seconds,
        "enabled" if ssl_mode else "disabled" if ssl_mode is False else "default",
    )

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("DB pool init attempt %s/%s", attempt, max_attempts)
            pool = await asyncpg.create_pool(
                dsn=database_url,
                min_size=1,
                max_size=10,
                command_timeout=10,
                max_inactive_connection_lifetime=30,
                ssl=ssl_mode,
            )
            logger.info("DB pool init success on attempt %s/%s", attempt, max_attempts)
            return pool
        except Exception as exc:
            last_error = exc
            logger.exception("DB pool init failed on attempt %s/%s", attempt, max_attempts)
            if attempt < max_attempts:
                await asyncio.sleep(retry_delay_seconds)

    logger.critical("DB pool init failed after %s attempts; service cannot start safely", max_attempts)
    raise RuntimeError("Database pool initialization failed") from last_error
