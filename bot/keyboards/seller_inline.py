from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def cars_list_kb(cars):
    keyboard = []

    for car in cars:
        keyboard.append([
            InlineKeyboardButton(
                text=f"{car['brand']} {car['model']}",
                callback_data=f"car_{car['id']}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def car_actions_kb(car_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редагувати опис",
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
