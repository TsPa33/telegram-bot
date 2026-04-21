from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ================= BUYER =================

def model_kb(models):
    rows = []

    for model in models:
        rows.append([
            InlineKeyboardButton(
                text=model["name"],
                callback_data=f"buyer:model:{model['id']}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_kb_with_back(models):
    rows = []

    for model in models:
        rows.append([
            InlineKeyboardButton(
                text=model["name"],
                callback_data=f"buyer:model:{model['id']}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="nav:back"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ================= SELLER (на майбутнє) =================

def model_kb_seller(models):
    rows = []

    for model in models:
        rows.append([
            InlineKeyboardButton(
                text=model["name"],
                callback_data=f"seller:model:{model['id']}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="➕ Додати модель",
            callback_data="seller:add_model"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)
