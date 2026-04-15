from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ================= BRAND =================

def brand_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Підтвердити",
                callback_data=f"brand:ok:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Відхилити",
                callback_data=f"brand:no:{request_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Редагувати",
                callback_data=f"brand:edit:{request_id}"
            )
        ]
    ])


# ================= MODEL =================

def model_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Підтвердити",
                callback_data=f"model:ok:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Відхилити",
                callback_data=f"model:no:{request_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Редагувати",
                callback_data=f"model:edit:{request_id}"
            )
        ]
    ])


# ================= 🔐 VERIFICATION =================

def verification_request_kb(seller_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Верифікувати",
                callback_data=f"verify:ok:{seller_id}"
            ),
            InlineKeyboardButton(
                text="❌ Відхилити",
                callback_data=f"verify:no:{seller_id}"
            )
        ]
    ])
