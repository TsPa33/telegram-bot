from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def brand_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="BMW"), KeyboardButton(text="Audi")],
            [KeyboardButton(text="Toyota")]
        ],
        resize_keyboard=True
    )
