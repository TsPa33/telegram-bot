from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def model_keyboard(brand: str):
    models = {
        "BMW": ["E60", "E90", "F10"],
        "Audi": ["A4", "A6", "A100"],
        "Toyota": ["Camry", "Corolla"]
    }

    buttons = [
        [KeyboardButton(text=model)]
        for model in models.get(brand, [])
    ]

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
