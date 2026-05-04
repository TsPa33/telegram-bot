from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ================= EXISTING =================

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


# ================= NEW: USERS =================

def admin_users_kb(users):
    """
    Список користувачів
    """
    buttons = []

    for u in users:
        label = f"{u['id']} | {u.get('username') or 'no_name'}"

        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"admin:user:{u['id']}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_user_actions_kb(user_id: int):
    """
    Дії над користувачем
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="👁 Переглянути",
                callback_data=f"admin:view:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Видалити",
                callback_data=f"admin:delete:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅ Назад",
                callback_data="admin:users"
            )
        ]
    ])


def admin_confirm_delete_kb(user_id: int):
    """
    Підтвердження видалення
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚠️ Підтвердити видалення",
                callback_data=f"admin:delete_confirm:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Скасувати",
                callback_data=f"admin:user:{user_id}"
            )
        ]
    ])
