from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.config import ADMINS


def start_keyboard(user_id: int):
    buttons = [
        [KeyboardButton(text="Поїхали 🚀")]
    ]

    # 🔥 КНОПКА АДМІНА
    if user_id in ADMINS:
        buttons.append([KeyboardButton(text="⚙️ Адмін панель")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
