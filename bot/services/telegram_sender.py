from aiogram import Bot
from bot.config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)


async def send_message_to_seller(telegram_id: int, text: str):
    try:
        await bot.send_message(chat_id=telegram_id, text=text)
    except Exception as e:
        print("SEND ERROR:", e)
