from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def model_kb(models):
    rows = [
        [InlineKeyboardButton(text=model["name"], callback_data=f"buyer:model:{model['id']}")]
        for model in models
    ]
    rows.append([InlineKeyboardButton(text="➕ Додати модель", callback_data="buyer:add_model")])
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def model_kb_with_back(models):
    rows = [
        [InlineKeyboardButton(text=model["name"], callback_data=f"buyer:model:{model['id']}")]
        for model in models
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
