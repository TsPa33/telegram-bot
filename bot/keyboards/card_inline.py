from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_card_keyboard(username: str | None, page: int, total: int):
    rows = []

    if total > 1:
        nav = []

        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=f"page:{page-1}"
            ))

        nav.append(InlineKeyboardButton(
            text=f"{page+1}/{total}",
            callback_data="noop"
        ))

        if page < total - 1:
            nav.append(InlineKeyboardButton(
                text="➡️",
                callback_data=f"page:{page+1}"
            ))

        rows.append(nav)

    if username:
        rows.append([
            InlineKeyboardButton(
                text="📩 Написати продавцю",
                url=f"https://t.me/{username}"
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="⚠️ Контакт відсутній",
                callback_data="noop"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)
