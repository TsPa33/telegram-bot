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
from bot.database.pool import init_pool
from bot.database.models import create_tables

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


async def get_storage():
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return RedisStorage(from_url(redis_url))
    return MemoryStorage()


async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    await init_pool()
    await create_tables()

    dp = Dispatcher(storage=await get_storage())
    bot = Bot(token=BOT_TOKEN)

    await bot.delete_webhook(drop_pending_updates=True)

    dp.callback_query.middleware(CallbackAnswerMiddleware())
    dp.errors.register(global_error_handler)

    # ✅ ЄДИНА ПРАВИЛЬНА СХЕМА ROUTERS
    dp.include_router(start_router)
    dp.include_router(support_router)
    dp.include_router(seller_router)  # ← тут вже підключені cms + media
    dp.include_router(admin_router)
    dp.include_router(buyer_router)
    dp.include_router(router)

    logger.info("🚀 BOT STARTED")

    await dp.start_polling(bot)


async def run_api():
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(app=app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    if os.getenv("RUN_API", "1") == "1":
        await asyncio.gather(run_bot(), run_api())
    else:
        await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
