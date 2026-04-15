import asyncio
import logging
import traceback
import os

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from redis.asyncio import from_url

from bot.config import BOT_TOKEN
from bot.handlers import start, seller, buyer, admin
from bot.database.pool import init_pool


# ================= LOGGING =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ================= ERROR HANDLER =================

async def global_error_handler(event: types.Update, exception: Exception):
    error_text = "".join(
        traceback.format_exception(type(exception), exception, exception.__traceback__)
    )

    logger.error("🚨 GLOBAL ERROR:\n%s", error_text)

    try:
        if event.message:
            await event.message.answer("⚠️ Сталась помилка")
        elif event.callback_query:
            await event.callback_query.answer("⚠️ Помилка", show_alert=True)
    except Exception:
        pass

    return True


# ================= REDIS =================

async def get_storage():
    redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        logger.warning("⚠️ REDIS_URL not found → fallback MemoryStorage")
        return MemoryStorage()

    try:
        redis = from_url(redis_url)

        # тест підключення
        await redis.ping()

        logger.info("✅ Redis connected (Railway)")

        return RedisStorage(redis)

    except Exception as e:
        logger.warning("⚠️ Redis connection failed → fallback MemoryStorage")
        logger.warning(e)

        return MemoryStorage()


# ================= RUN BOT =================

async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    await init_pool()

    storage = await get_storage()

    dp = Dispatcher(storage=storage)
    bot = Bot(token=BOT_TOKEN)

    dp.errors.register(global_error_handler)

    dp.include_router(start.router)
    dp.include_router(seller.router)
    dp.include_router(admin.router)
    dp.include_router(buyer.router)

    logger.info("🚀 BOT STARTED")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


# ================= ENTRY =================

async def main():
    await asyncio.sleep(2)
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
