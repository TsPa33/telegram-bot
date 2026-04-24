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
                    callback_data=f"car_edit:{car_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Видалити",
                    callback_data=f"delete:{car_id}"
                )
            ]
        ]
    )


# ================= PROFILE EDIT =================

def profile_edit_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏪 Назва магазину", callback_data="edit:shop_name")],

            [InlineKeyboardButton(text="👤 Ім’я", callback_data="edit:name")],
            [InlineKeyboardButton(text="📞 Телефон", callback_data="edit:phone")],
            [InlineKeyboardButton(text="🌐 Сайт", callback_data="edit:website")],

            [InlineKeyboardButton(text="📍 Місто", callback_data="edit:city")],
            [InlineKeyboardButton(text="🖼 Фото", callback_data="edit:photo")],
            [InlineKeyboardButton(text="📝 Опис", callback_data="edit:description")],

            # 🔥 управління
            [InlineKeyboardButton(text="⬅️ До профілю", callback_data="edit:back")],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="edit:cancel")],
        ]
    )


def profile_cancel_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="edit:cancel")],
            [InlineKeyboardButton(text="⬅️ До профілю", callback_data="edit:back")],
        ]
    )
