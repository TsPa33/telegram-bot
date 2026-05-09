from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.roles import is_admin, is_seller


async def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    seller = await is_seller(user_id)
    admin = await is_admin(user_id)

    buttons: list[list[InlineKeyboardButton]] = []

    # ================= ROLES =================

    # покупець
    buttons.append([
        InlineKeyboardButton(
            text="🚗 Покупець",
            callback_data="role:buyer"
        )
    ])

    # продавець
    if seller:
        buttons.append([
            InlineKeyboardButton(
                text="🏪 Продавець",
                callback_data="role:seller"
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text="🏪 Стати продавцем",
                callback_data="role:seller"
            )
        ])

    # ================= DEMO =================

    buttons.append([
        InlineKeyboardButton(
            text="🌐 Демо сайти",
            callback_data="demo:sites"
        )
    ])

    # ================= ADMIN =================

    if admin:
        buttons.append([
            InlineKeyboardButton(
                text="⚙️ Панель адміністратора",
                callback_data="nav:admin"
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )
