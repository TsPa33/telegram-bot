import asyncio
import logging
import traceback
import os

from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.types import CallbackQuery, ErrorEvent
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from redis.asyncio import from_url
from redis.exceptions import RedisError

from bot.config import BOT_TOKEN, DATABASE_URL
from bot.database.pool import init_pool
from bot.database import pool as pool_module
from bot.database.models import create_tables
from bot.database.migrations_runner import run_sql_migrations

from bot.handlers.start import router as start_router
from bot.handlers.seller import router as seller_router
from bot.handlers.buyer import router as buyer_router
from bot.handlers.admin import router as admin_router
from bot.handlers.support import router as support_router

import uvicorn
from bot.api.app import app

print("🔥 CLEAN MAIN LOADED")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)
router = Router()


class UpdateLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        state = data.get("state")
        current_state = None
        if state is not None:
            try:
                current_state = await state.get_state()
            except Exception:
                current_state = "<state_error>"

        if hasattr(event, "text"):
            logger.info("INCOMING message user_id=%s chat_id=%s text=%r state=%s",
                        getattr(getattr(event, "from_user", None), "id", None),
                        getattr(getattr(event, "chat", None), "id", None),
                        getattr(event, "text", None),
                        current_state)
        elif hasattr(event, "data"):
            logger.info("INCOMING callback user_id=%s chat_id=%s data=%r state=%s",
                        getattr(getattr(event, "from_user", None), "id", None),
                        getattr(getattr(getattr(event, "message", None), "chat", None), "id", None),
                        getattr(event, "data", None),
                        current_state)

        return await handler(event, data)



@router.callback_query(F.data.startswith("debug:"))
async def debug_all_callbacks(callback: CallbackQuery):
    print("🔥 CALLBACK:", callback.data)


async def global_error_handler(event: ErrorEvent):
    logger.error("Exception occurred", exc_info=event.exception)
    traceback.print_exception(
        type(event.exception),
        event.exception,
        event.exception.__traceback__,
    )


class RedisFallbackStorage(BaseStorage):
    def __init__(self, primary: BaseStorage, fallback: BaseStorage):
        self._primary = primary
        self._fallback = fallback
        self._degraded = False

    async def _run_with_fallback(self, method_name: str, *args, **kwargs):
        storage = self._fallback if self._degraded else self._primary
        method = getattr(storage, method_name)
        try:
            return await method(*args, **kwargs)
        except RedisError:
            if not self._degraded:
                logger.warning("Redis unavailable, falling back to MemoryStorage")
                self._degraded = True
                return await getattr(self._fallback, method_name)(*args, **kwargs)
            raise

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._run_with_fallback("set_state", key, state)

    async def get_state(self, key: StorageKey) -> str | None:
        return await self._run_with_fallback("get_state", key)

    async def set_data(self, key: StorageKey, data: dict) -> None:
        await self._run_with_fallback("set_data", key, data)

    async def get_data(self, key: StorageKey) -> dict:
        return await self._run_with_fallback("get_data", key)

    async def close(self) -> None:
        await self._primary.close()
        await self._fallback.close()


async def get_storage():
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        redis = from_url(
            redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False,
        )
        try:
            await redis.ping()
            return RedisFallbackStorage(RedisStorage(redis), MemoryStorage())
        except RedisError:
            logger.warning("Redis unavailable, falling back to MemoryStorage")
            await redis.aclose()
    return MemoryStorage()


async def run_bot():
    logger.info("BOT_TOKEN present: %s", "yes" if BOT_TOKEN else "no")
    logger.info("DATABASE_URL present: %s", "yes" if DATABASE_URL else "no")
    if not BOT_TOKEN:
        logger.error("Bot cannot start: BOT_TOKEN is not set")
        raise RuntimeError("BOT_TOKEN is not set")

    try:
        await init_pool()
        await create_tables()
        await run_sql_migrations()
    except Exception:
        logger.critical("Fatal DB startup error; bot polling will not start", exc_info=True)
        raise

    disable_polling_advisory_lock = os.getenv("DISABLE_POLLING_ADVISORY_LOCK") == "1"
    lock_conn = None
    got_lock = False

    if disable_polling_advisory_lock:
        logger.info("Polling advisory lock disabled by env")
    else:
        try:
            lock_conn = await pool_module.pool.acquire()
            got_lock = await lock_conn.fetchval("SELECT pg_try_advisory_lock($1)", 2026051501)
            if not got_lock:
                logger.warning("Telegram polling is already running in another process; skipping bot startup here")
                await pool_module.pool.release(lock_conn)
                return
        except Exception:
            logger.critical("Could not acquire polling advisory lock; bot polling will not start", exc_info=True)
            raise

    dp = Dispatcher(storage=await get_storage())
    bot = Bot(token=BOT_TOKEN)

    try:
        await bot.delete_webhook(drop_pending_updates=True)

        dp.message.outer_middleware(UpdateLoggingMiddleware())
        dp.callback_query.outer_middleware(UpdateLoggingMiddleware())
        dp.callback_query.middleware(CallbackAnswerMiddleware())
        dp.errors.register(global_error_handler)

        # ✅ ЄДИНА ПРАВИЛЬНА СХЕМА ROUTERS
        dp.include_router(start_router)
        dp.include_router(support_router)
        logger.info("Including seller_router into dispatcher seller_router_id=%s", id(seller_router))
        dp.include_router(seller_router)  # ← тут вже підключені cms + media
        dp.include_router(admin_router)
        dp.include_router(buyer_router)
        dp.include_router(router)

        logger.info("/start handler registered via start_router")
        logger.info("Bot polling starting")

        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        if lock_conn is not None:
            try:
                if got_lock:
                    await lock_conn.execute("SELECT pg_advisory_unlock($1)", 2026051501)
            finally:
                await pool_module.pool.release(lock_conn)


async def run_api():
    port = int(os.getenv("PORT", 8000))
    logger.info("API started on port %s", port)
    config = uvicorn.Config(app=app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    logger.info("Startup mode RUN_API=%s", os.getenv("RUN_API", "1"))
    try:
        if os.getenv("RUN_API", "1") == "1":
            await asyncio.gather(run_bot(), run_api())
        else:
            await run_bot()
    except Exception:
        logger.critical("Service startup failed; Railway process will exit", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
