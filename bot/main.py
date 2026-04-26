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
from bot.handlers import start, buyer, admin
from bot.handlers.seller import router as seller_router

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
    logger.error("Exception occurred", exc_info=event.exception)
    traceback.print_exception(type(event.exception), event.exception, event.exception.__traceback__)


async def get_storage():
    redis_url = os.getenv("REDIS_URL")

    if redis_url:
        redis = from_url(redis_url)
        return RedisStorage(redis)
    else:
        return MemoryStorage()


async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    print("DB:", os.getenv("DATABASE_URL"))

    await init_pool()
    await create_tables()

    storage = await get_storage()

    dp = Dispatcher(storage=storage)
    bot = Bot(token=BOT_TOKEN)

    await bot.delete_webhook(drop_pending_updates=True)

    dp.callback_query.middleware(CallbackAnswerMiddleware())
    dp.errors.register(global_error_handler)

    # ✅ ПРАВИЛЬНИЙ ПОРЯДОК
    dp.include_router(start.router)
    dp.include_router(seller_router)  # 🔥 ЄДИНИЙ seller router
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


if __name__ == "__main__":
    asyncio.run(run_bot())
