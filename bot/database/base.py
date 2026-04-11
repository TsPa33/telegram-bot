import asyncio
from contextlib import asynccontextmanager
from typing import Any, List, Optional

from . import pool as pool_module


# ================= BASIC =================

async def fetch(query: str, *args) -> List[Any]:
    async with pool_module.pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args) -> Optional[Any]:
    async with pool_module.pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args) -> str:
    async with pool_module.pool.acquire() as conn:
        return await conn.execute(query, *args)


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
