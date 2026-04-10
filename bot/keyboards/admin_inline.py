from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def brand_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"brand_ok_{request_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"brand_no_{request_id}")
        ],
        [
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"brand_edit_{request_id}")
        ]
    ])


def model_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Approve", callback_data=f"model_ok_{request_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"model_no_{request_id}")
        ],
        [
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"model_edit_{request_id}")
        ]
    ])
