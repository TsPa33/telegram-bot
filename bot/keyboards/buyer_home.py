from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def buyer_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Знайти авто", callback_data="buyer:find")],
            [InlineKeyboardButton(text="🛠 Знайти послугу", callback_data="buyer:services")],
            [
                InlineKeyboardButton(text="❤️ Обране", callback_data="buyer:favorites"),
                InlineKeyboardButton(text="📩 Мої заявки", callback_data="buyer:requests"),
            ],
            [
                InlineKeyboardButton(text="🚘 Мій гараж", callback_data="buyer:garage"),
                InlineKeyboardButton(text="👤 Профіль", callback_data="buyer:profile"),
            ],
            [InlineKeyboardButton(text="💬 Підтримка", callback_data="support:open")],
        ]
    )
