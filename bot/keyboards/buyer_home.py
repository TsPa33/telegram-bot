from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def buyer_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Почати пошук", callback_data="buyer:find")],
            [InlineKeyboardButton(text="📋 Мої заявки", callback_data="buyer:requests")],
            [InlineKeyboardButton(text="🕘 Історія пошуку", callback_data="buyer:history")],
            [InlineKeyboardButton(text="💬 Підтримка", callback_data="support:open")],
            [InlineKeyboardButton(text="↩️ Головне меню", callback_data="nav:main")],
        ]
    )
