import asyncio
import logging
import traceback

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage

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
    error_text = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))

    logger.error("🚨 GLOBAL ERROR:\n%s", error_text)

    try:
        if event.message:
            await event.message.answer("⚠️ Сталась помилка. Ми вже працюємо над цим.")
        elif event.callback_query:
            await event.callback_query.answer("⚠️ Помилка", show_alert=True)
    except Exception:
        logger.error("❌ Failed to notify user about error")

    return True  # IMPORTANT: prevents crash


# ================= RUN BOT =================

async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    await init_pool()

    dp = Dispatcher(storage=MemoryStorage())
    bot = Bot(token=BOT_TOKEN)

    # 🔴 REGISTER GLOBAL ERROR HANDLER
    dp.errors.register(global_error_handler)

    # routers
    dp.include_router(start.router)
    dp.include_router(seller.router)
    dp.include_router(admin.router)
    dp.include_router(buyer.router)

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
