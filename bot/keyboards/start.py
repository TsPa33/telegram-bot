from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def start_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поїхали 🚀")]
        ],
        resize_keyboard=True
    )
