from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def buyer_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Почати пошук", callback_data="buyer:find")],
            [InlineKeyboardButton(text="💬 Мої повідомлення", callback_data="buyer:messages")],
            [InlineKeyboardButton(text="📋 Мої заявки", callback_data="buyer:requests")],
            [InlineKeyboardButton(text="🕘 Історія запитів", callback_data="buyer:history")],
            [InlineKeyboardButton(text="💬 Підтримка", callback_data="support:open")],
            [InlineKeyboardButton(text="↩️ Головне меню", callback_data="nav:main")],
        ]
    )
