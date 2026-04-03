import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import BOT_TOKEN
from bot.handlers import start
from bot.database.models import create_tables


logging.basicConfig(level=logging.INFO)


async def run_bot():
    # перевірка токена
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    # ініціалізація БД (в окремому потоці)
    await asyncio.to_thread(create_tables)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start.router)

    logging.info("BOT STARTED")

    await dp.start_polling(bot)


def main():
    asyncio.run(run_bot())
