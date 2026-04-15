from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def brand_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"brand:ok:{request_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"brand:no:{request_id}")
        ],
        [
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"brand:edit:{request_id}")
        ]
    ])


def model_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"model:ok:{request_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"model:no:{request_id}")
        ],
        [
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"model:edit:{request_id}")
        ]
    ])


def verification_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"verify:ok:{request_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"verify:no:{request_id}")
        ]
    ])
