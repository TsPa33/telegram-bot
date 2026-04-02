from aiogram.utils.keyboard import InlineKeyboardBuilder


def contact_button(username: str):
    kb = InlineKeyboardBuilder()

    if username:
        kb.button(
            text="Написати продавцю",
            url=f"https://t.me/{username}"
        )

    return kb.as_markup()
