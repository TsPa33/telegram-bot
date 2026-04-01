import asyncio
from aiogram import Bot, Dispatcher

from config import TOKEN
from handlers import register_handlers

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    register_handlers(dp)

    print("Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())