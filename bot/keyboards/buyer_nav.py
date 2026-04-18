from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def buyer_nav_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
                InlineKeyboardButton(text="🔄 Новий пошук", callback_data="nav:restart"),
            ],
            [
                InlineKeyboardButton(text="🏪 Стати продавцем", callback_data="nav:seller"),
                InlineKeyboardButton(text="🏠 Головне меню", callback_data="nav:home"),
            ],
        ]
    )
