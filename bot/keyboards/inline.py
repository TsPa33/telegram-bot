from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ================= BUYER =================

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


# ================= SELLER =================

def cars_list_kb(cars):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{car['brand']} {car['model']}",
                    callback_data=f"car_{car['id']}"
                )
            ]
            for car in cars
        ]
    )


def car_actions_kb(car_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit_{car_id}")],
            [InlineKeyboardButton(text="❌ Видалити", callback_data=f"delete_{car_id}")]
        ]
    )
