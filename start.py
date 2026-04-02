import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

print("STARTING BOT...")

BOT_TOKEN = os.getenv("BOT_TOKEN")
print("TOKEN:", BOT_TOKEN)

dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привіт! Я працюю 🚀")

async def main():
    print("RUNNING MAIN...")
    bot = Bot(token=BOT_TOKEN)
    print("BOT CREATED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
