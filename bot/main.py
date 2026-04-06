import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN
from bot.handlers import start, seller, buyer
from bot.database.models import create_tables

logging.basicConfig(level=logging.INFO)


async def run_bot():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    # БД
    await asyncio.to_thread(create_tables)

    # FSM storage
    dp = Dispatcher(storage=MemoryStorage())

    bot = Bot(token=BOT_TOKEN)

    # routers
    dp.include_router(start.router)
    dp.include_router(seller.router)
    dp.include_router(buyer.router)

    logging.info("BOT STARTED")

    await dp.start_polling(bot)


def main():
    asyncio.run(run_bot())
