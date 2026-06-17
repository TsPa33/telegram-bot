import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, List, Optional, TypeVar

import asyncpg

from . import pool as pool_module

logger = logging.getLogger(__name__)
T = TypeVar("T")


# ================= BASIC =================

async def _run_db(operation: Callable[[], Awaitable[T]]) -> T:
    if pool_module.pool is None:
        raise RuntimeError("Database pool is not initialized")
    try:
        return await operation()
    except (ConnectionResetError, asyncpg.PostgresConnectionError, asyncpg.InterfaceError) as exc:
        logger.warning("Database connection error, retrying once: %s", exc.__class__.__name__)
        return await operation()


async def fetch(query: str, *args) -> List[Any]:
    async def operation():
        async with pool_module.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    return await _run_db(operation)


async def fetchrow(query: str, *args) -> Optional[Any]:
    async def operation():
        async with pool_module.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    return await _run_db(operation)


async def execute(query: str, *args) -> str:
    async def operation():
        async with pool_module.pool.acquire() as conn:
            return await conn.execute(query, *args)

    return await _run_db(operation)


# ================= TRANSACTION =================

@asynccontextmanager
async def transaction():
    """
    Використовувати коли потрібно кілька SQL операцій як одна атомарна.
    """
    async with pool_module.pool.acquire() as conn:
        async with conn.transaction():
            yield conn


# ================= SAFE WRAPPERS =================

async def safe_fetch(query: str, *args, timeout: float = 5.0):
    return await _with_timeout(fetch(query, *args), timeout)


async def safe_fetchrow(query: str, *args, timeout: float = 5.0):
    return await _with_timeout(fetchrow(query, *args), timeout)


async def safe_execute(query: str, *args, timeout: float = 5.0):
    return await _with_timeout(execute(query, *args), timeout)


async def _with_timeout(coro, timeout: float):
    try:
        return await asyncio.wait_for(coro, timeout)
    except asyncio.TimeoutError:
        raise RuntimeError("Database timeout")
