from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.services.roles import is_admin


async def start_keyboard(user_id: int):
    buttons = [
        [KeyboardButton(text="Поїхали 🚀")]
    ]

    # ✅ FIX: async check
    if await is_admin(user_id):
        buttons.append([KeyboardButton(text="⚙️ Адмін панель")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
