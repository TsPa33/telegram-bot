import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.handlers import start, seller, buyer
from bot.database.models import create_tables
from bot.database.db import init_db
from bot.handlers import admin

logging.basicConfig(level=logging.INFO)


async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    # await asyncio.to_thread(create_tables)
    
    init_db() 

    dp = Dispatcher(storage=MemoryStorage())
bot = Bot(token=BOT_TOKEN)

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
    # Дає старому процесу закритись (критично для Railway)
    await asyncio.sleep(2)
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
