from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def brand_kb(brands):
    rows = [
        [InlineKeyboardButton(text=brand["name"], callback_data=f"buyer:brand:{brand['id']}")]
        for brand in brands
    ]
    rows.append([InlineKeyboardButton(text="➕ Додати бренд", callback_data="buyer:add_brand")])
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )
