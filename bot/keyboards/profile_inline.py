from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def profile_edit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏪 Назва магазину", callback_data="edit:shop_name")],
            [InlineKeyboardButton(text="👤 Ім’я", callback_data="edit:name")],
            [InlineKeyboardButton(text="📞 Телефон", callback_data="edit:phone")],
            [InlineKeyboardButton(text="🌐 Сайт", callback_data="edit:website")],
            [InlineKeyboardButton(text="📍 Місто", callback_data="edit:city")],
            [InlineKeyboardButton(text="🖼 Фото", callback_data="edit:photo")],
            [InlineKeyboardButton(text="📝 Опис", callback_data="edit:description")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="edit:back")],
        ]
    )


def profile_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="edit:cancel")]
        ]
    )
