from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.roles import is_admin, is_seller


async def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    seller = await is_seller(user_id)
    admin = is_admin(user_id)

    buttons: list[list[InlineKeyboardButton]] = []

    if not seller:
        buttons.append([
            InlineKeyboardButton(text="🚗 Шукати розборку", callback_data="buyer:find"),
            InlineKeyboardButton(text="🏪 Стати продавцем", callback_data="nav:seller"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="🏪 Мій гараж", callback_data="nav:garage"),
            InlineKeyboardButton(text="🚗 Знайти розборку", callback_data="buyer:find"),
        ])

    if admin:
        buttons.append([
            InlineKeyboardButton(text="⚙️ Панель адміністратора", callback_data="nav:admin")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
