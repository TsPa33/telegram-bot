import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.handlers import start, seller, buyer, admin
from bot.database.pool import init_pool

logging.basicConfig(level=logging.INFO)


async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    await init_pool()

    dp = Dispatcher(storage=MemoryStorage())
    bot = Bot(token=BOT_TOKEN)

    # routers
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(buyer.router)
    dp.include_router(seller.router)

    logging.info("BOT STARTED")

    try:
        await dp.start_polling(bot)
    finally:
        logging.info("Shutting down bot...")
        await bot.session.close()


async def main():
    await asyncio.sleep(2)
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
