from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def seller_main_kb(is_verified: bool = False):
    buttons = []

    if not is_verified:
        buttons.append([
            KeyboardButton(text="🔐 Верифікація")
        ])

    buttons.extend([
        [
            KeyboardButton(text="➕ Додати авто"),
            KeyboardButton(text="➕ Додати послугу"),
        ],
        [
            KeyboardButton(text="📋 Мій гараж"),
            KeyboardButton(text="📋 Мої послуги"),
        ],
        [
            KeyboardButton(text="👤 Мій профіль"),
            KeyboardButton(text="📊 Статистика"),
        ],
        [
            KeyboardButton(text="🌐 Мій сайт"),
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


# 🔥 ГОЛОВНЕ МЕНЮ САЙТУ (CMS)
def site_menu_kb(subdomain: str, is_active: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✏️ Шапка", callback_data="site:edit:header")],
        [InlineKeyboardButton(text="🧱 Про нас", callback_data="site:toggle:about")],

        # 🔥 НОВІ ДІЇ В САЙТІ
        [InlineKeyboardButton(text="🖼 Банери", callback_data="site:edit:banners")],
        [InlineKeyboardButton(text="🖼 Лого", callback_data="site:edit:logo")],

        [InlineKeyboardButton(text="🚀 Опублікувати", callback_data="site:publish")],
    ]

    if is_active:
        buttons.append([
            InlineKeyboardButton(
                text="🌍 Відкрити сайт",
                url=f"https://worker-production-e30f.up.railway.app/site/{subdomain}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
