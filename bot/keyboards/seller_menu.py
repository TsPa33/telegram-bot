from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def seller_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Додати авто")],
            [KeyboardButton(text="📋 Мої авто")],
            [KeyboardButton(text="👤 Профіль")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔐 Верифікація")]
        ],
        resize_keyboard=True
    )
