import asyncpg
import os

pool: asyncpg.Pool | None = None


async def init_pool():
    global pool

    pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=1,
        max_size=10
    )
