from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def buyer_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Знайти авто", callback_data="buyer:find")],
            [InlineKeyboardButton(text="👀 Мої перегляди", callback_data="buyer:views")],
            [InlineKeyboardButton(text="⭐ Обрані", callback_data="buyer:favorites")],
            [InlineKeyboardButton(text="👤 Профіль", callback_data="buyer:profile")],
        ]
    )
