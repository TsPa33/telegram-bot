import asyncio
import logging
import traceback
import os

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import CallbackQuery, ErrorEvent
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from redis.asyncio import from_url

from bot.config import BOT_TOKEN
from bot.handlers import start, seller, buyer, admin

from bot.database.pool import init_pool
from bot.database.models import create_tables

import uvicorn
from bot.api.app import app

print("🔥 VERSION FIXED SELLER ROUTER LOADED")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("debug:"))
async def debug_all_callbacks(callback: CallbackQuery):
    print("🔥 CALLBACK CAUGHT:", callback.data)


# ================= ERROR HANDLER =================

async def global_error_handler(event: ErrorEvent):
    exception = event.exception
    update = event.update

    error_text = "".join(
        traceback.format_exception(type(exception), exception, exception.__traceback__)
    )

    logger.error("🚨 GLOBAL ERROR:\n%s", error_text)

    try:
        if update.message:
            await update.message.answer("⚠️ Сталась помилка")
        elif update.callback_query:
            await update.callback_query.answer("⚠️ Помилка", show_alert=True)
    except Exception:
        logger.error("❌ Failed to notify user")

    return True


# ================= REDIS =================

async def get_storage():
    redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        logger.warning("⚠️ REDIS_URL not found → fallback MemoryStorage")
        return MemoryStorage()

    try:
        redis = from_url(redis_url)
        await redis.ping()

        logger.info("✅ Redis connected")
        return RedisStorage(redis)

    except Exception as e:
        logger.warning("⚠️ Redis connection failed → fallback MemoryStorage")
        logger.warning(e)
        return MemoryStorage()


# ================= BOT =================

async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    print("DB:", os.getenv("DATABASE_URL"))

    await init_pool()
    await create_tables()

    storage = await get_storage()

    dp = Dispatcher(storage=storage)
    bot = Bot(token=BOT_TOKEN)

    # Drop queued updates (including stale callback queries) to prevent
    # old button presses from re-triggering flows after restart.
    await bot.delete_webhook(drop_pending_updates=True)

    dp.callback_query.middleware(CallbackAnswerMiddleware())
    dp.errors.register(global_error_handler)

    # 🔥 ПОРЯДОК ВАЖЛИВИЙ
    dp.include_router(start.router)

    dp.include_router(seller.router)       # інші seller модулі

    dp.include_router(admin.router)
    dp.include_router(buyer.router)
    dp.include_router(router)

    logger.info("🚀 BOT STARTED")

    await dp.start_polling(bot)


# ================= API =================

async def run_api():
    port = int(os.getenv("PORT", 8000))

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


# ================= ENTRY =================

async def main():
    await asyncio.sleep(2)

    await asyncio.gather(
        run_bot(),
        run_api()
    )


if __name__ == "__main__":
    asyncio.run(main())
