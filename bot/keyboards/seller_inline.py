from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ================= LIST OF CARS =================

def cars_list_kb(cars):
    """
    Список авто продавця
    """
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


# ================= ACTIONS =================

def car_actions_kb(car_id: int):
    """
    Дії над авто
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редагувати",
                    callback_data=f"edit_{car_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Видалити",
                    callback_data=f"delete_{car_id}"
                )
            ]
        ]
    )
