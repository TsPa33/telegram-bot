from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def model_kb(models):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=model["name"], callback_data=f"buyer:model:{model['id']}")]
            for model in models
        ]
    )
