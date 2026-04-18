from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import is_admin
from bot.database.base import fetch


async def is_seller(telegram_id: int) -> bool:
    row = await fetch(
        "SELECT id FROM sellers WHERE telegram_id = $1 LIMIT 1",
        telegram_id
    )
    return bool(row)


async def buyer_nav_kb(user_id: int) -> InlineKeyboardMarkup:
    seller = await is_seller(user_id)

    if seller:
        seller_button = InlineKeyboardButton(
            text="🏪 Мій гараж",
            callback_data="nav:garage"
        )
    else:
        seller_button = InlineKeyboardButton(
            text="🏪 Стати продавцем",
            callback_data="nav:seller"
        )

    inline_keyboard = [
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="🔄 Новий пошук", callback_data="nav:restart"),
        ],
        [
            seller_button,
        ],
    ]

    if is_admin(user_id):
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Адмін панель",
                    callback_data="nav:admin"
                )
            ]
        )

    inline_keyboard.append(
        [
            InlineKeyboardButton(text="🏠 Головне меню", callback_data="nav:home"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
