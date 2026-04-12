from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ================= CAR LIST =================

def cars_list_kb(cars: list):
    rows = []

    for car in cars:
        rows.append([
            InlineKeyboardButton(
                text=f"{car['brand']} {car['model']}",
                callback_data=f"car:{car['id']}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ================= SELLER ACTIONS =================

def seller_card_actions_kb(car_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редагувати",
                    callback_data=f"edit:{car_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Видалити",
                    callback_data=f"delete:{car_id}"
                )
            ]
        ]
    )


# ================= OPTIONAL (LEGACY SUPPORT) =================
# Якщо десь ще використовується старий формат

def car_actions_kb(car_id: int):
    return seller_card_actions_kb(car_id)
