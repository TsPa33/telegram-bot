from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def brand_kb(brands):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=brand["name"], callback_data=f"buyer:brand:{brand['id']}")]
            for brand in brands
        ]
    )
