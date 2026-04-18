import asyncio
import logging
import traceback
import os

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from redis.asyncio import from_url

from bot.config import BOT_TOKEN
from bot.handlers import start, seller, buyer, admin, profile
from bot.database.pool import init_pool
from bot.database.models import create_tables  # 🔥 ДОДАНО


# ================= LOGGING =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)


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


# ================= RUN BOT =================

async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    import os
    print("DB:", os.getenv("DATABASE_URL"))

    # 🔴 1. ІНІЦІАЛІЗАЦІЯ БД
    await init_pool()

    # 🔴 2. СТВОРЕННЯ ТАБЛИЦЬ
    await create_tables()

    storage = await get_storage()

    dp = Dispatcher(storage=storage)
    bot = Bot(token=BOT_TOKEN)
    dp.callback_query.middleware(CallbackAnswerMiddleware())

    dp.errors.register(global_error_handler)

    dp.include_router(start.router)
    dp.include_router(seller.router)
    dp.include_router(admin.router)
    dp.include_router(buyer.router)
    dp.include_router(profile.router)

    logger.info("🚀 BOT STARTED")

    try:
        await dp.start_polling(bot)
    finally:
        logger.info("🛑 Shutting down bot...")
        await bot.session.close()


# ================= ENTRY =================

async def main():
    await asyncio.sleep(2)
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
