from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def seller_main_kb(is_verified: bool = False):
    buttons = []

    # 🔐 якщо НЕ верифікований — зверху
    if not is_verified:
        buttons.append([
            KeyboardButton(text="🔐 Верифікація")
        ])

    # ✅ оновлений layout (з послугами)
    buttons.extend([
        [
            KeyboardButton(text="➕ Додати авто"),
            KeyboardButton(text="➕ Додати послугу"),  # ✅ NEW
        ],
        [
            KeyboardButton(text="📋 Мій гараж"),
            KeyboardButton(text="📋 Мої послуги"),  # ✅ NEW
        ],
        [
            KeyboardButton(text="👤 Мій профіль"),
            KeyboardButton(text="📊 Статистика"),
        ],
        [
            KeyboardButton(text="💳 Пакети послуг"),
            KeyboardButton(text="↩️ На головне меню"),
        ],
    ])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )


def seller_menu_kb(is_verified: bool = False):
    return seller_main_kb(is_verified=is_verified)
