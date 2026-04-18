from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def model_kb(models):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=model["name"], callback_data=f"buyer:model:{model['id']}")]
            for model in models
        ]
    )


def model_kb_with_back(models):
    rows = [
        [InlineKeyboardButton(text=model["name"], callback_data=f"buyer:model:{model['id']}")]
        for model in models
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
