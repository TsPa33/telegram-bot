from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def brand_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"admin:brand:ok:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Reject",
                callback_data=f"admin:brand:no:{request_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Edit",
                callback_data=f"admin:brand:edit:{request_id}"
            )
        ]
    ])


def model_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"admin:model:ok:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Reject",
                callback_data=f"admin:model:no:{request_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Edit",
                callback_data=f"admin:model:edit:{request_id}"
            )
        ]
    ])


def verification_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"admin:verify:ok:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Reject",
                callback_data=f"admin:verify:no:{request_id}"
            )
        ]
    ])
