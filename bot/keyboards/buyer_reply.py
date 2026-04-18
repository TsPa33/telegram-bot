from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def buyer_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True,
    )
