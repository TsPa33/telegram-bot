from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.config import is_admin


def start_keyboard(user_id: int):
    buttons = [
        [KeyboardButton(text="Поїхали 🚀")]
    ]

    # 🔥 КНОПКА АДМІНА
    if is_admin(user_id):
        buttons.append([KeyboardButton(text="⚙️ Адмін панель")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
