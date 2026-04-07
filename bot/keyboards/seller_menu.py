from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def seller_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Додати авто")],
            [KeyboardButton(text="📋 Мої авто")],
            [KeyboardButton(text="👤 Профіль")],
        ],
        resize_keyboard=True
    )
