from . import pool as pool_module


async def fetch(query: str, *args):
    async with pool_module.pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args):
    async with pool_module.pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args):
    async with pool_module.pool.acquire() as conn:
        return await conn.execute(query, *args)
