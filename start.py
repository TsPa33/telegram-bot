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
    await message.answer("Привіт! Я демо версія боту. Щоб я запрацював було потрібно 1.	Створення бота через Telegram (@BotFather)
	2.	Отримання BOT_TOKEN
	3.	Створення структури проєкту
	4.	Створення проєкту локально
	5.	Написання коду бота (start.py)
	6.	Створення requirements.txt
	7.	Створення Procfile
	8.	Ініціалізація Git репозиторію
	9.	Створення репозиторію на GitHub
	10.	Завантаження коду (commit + push)
	11.	Реєстрація / вхід у Railway
	12.	Створення проєкту в Railway
	13.	Підключення GitHub репозиторію
	14.	Налаштування змінних середовища (BOT_TOKEN)
	15.	Запуск деплою (Deploy)
	16.	Перевірка логів
	17.	Тест бота в Telegram (/start)")

async def main():
    print("RUNNING MAIN...")
    bot = Bot(token=BOT_TOKEN)
    print("BOT CREATED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
