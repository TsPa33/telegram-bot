import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

print("VERSION 2")

BOT_TOKEN = os.getenv("BOT_TOKEN")
print("TOKEN:", BOT_TOKEN)

dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привіт! Я демо версія боту 🚀\n\n"
        "Щоб я запрацював потрібно:\n"
        "1. Створити бота через @BotFather\n"
        "2. Отримати BOT_TOKEN\n"
        "3. Створити структуру проєкту\n"
        "4. Написати код бота\n"
        "5. Додати requirements.txt\n"
        "6. Додати Procfile\n"
        "7. Завантажити на GitHub\n"
        "8. Підключити до Railway\n"
        "9. Додати змінні середовища\n"
        "10. Запустити Deploy\n"
    )


async def main():
    print("RUNNING MAIN...")
    bot = Bot(token=BOT_TOKEN)
    print("BOT CREATED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
