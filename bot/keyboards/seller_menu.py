from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def seller_main_kb(is_verified: bool = False):
    buttons = []

    # 🔴 якщо НЕ верифікований — показуємо зверху
    if not is_verified:
        buttons.append([
            KeyboardButton(text="🔐 Верифікація")
        ])

    # основні кнопки
    buttons.extend([
        [KeyboardButton(text="➕ Додати авто")],
        [KeyboardButton(text="📋 Мої авто")],
        [KeyboardButton(text="👤 Профіль")],
        [KeyboardButton(text="📊 Статистика")]
    ])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )


def seller_menu_kb(is_verified: bool = False):
    return seller_main_kb(is_verified=is_verified)
