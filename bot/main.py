import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import BOT_TOKEN
from bot.handlers import start
from bot.database.models import create_tables


logging.basicConfig(level=logging.INFO)


async def run_bot():
    # 🔥 Ініціалізація БД (обов’язково першою)
    create_tables()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # підключаємо handlers
    dp.include_router(start.router)

    print("BOT STARTED")

    await dp.start_polling(bot)


def main():
    asyncio.run(run_bot())
