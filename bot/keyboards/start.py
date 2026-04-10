from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.config import ADMINS

def start_keyboard(user_id=None):
    buttons = [
        [KeyboardButton(text="Поїхали 🚀")]
    ]

    # 🔥 Додаємо кнопку для адміна
    if user_id in ADMINS:
        buttons.append([KeyboardButton(text="⚙️ Адмін панель")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
