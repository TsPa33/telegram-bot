from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def car_card_kb(username: str | None):
    buttons = []

    if username:
        buttons.append([
            InlineKeyboardButton(
                text="📩 Написати",
                url=f"https://t.me/{username}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="➡️ Далі", callback_data="next_page")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
