from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_card_keyboard(car: dict, page: int, total: int):
    rows = []

    if total > 1:
        nav = []

        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page:{page-1}"))

        nav.append(InlineKeyboardButton(text=f"{page+1}/{total}", callback_data="noop"))

        if page < total - 1:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page:{page+1}"))

        rows.append(nav)

    if car.get("phone"):
        rows.append([
            InlineKeyboardButton(text="📞 Подзвонити", callback_data=f"phone:{car['id']}")
        ])

    if car.get("website"):
        rows.append([
            InlineKeyboardButton(text="🌐 Сайт", callback_data=f"site:{car['id']}")
        ])

    if car.get("username"):
        rows.append([
            InlineKeyboardButton(text="✉️ Написати", url=f"https://t.me/{car['username']}")
        ])
    elif car.get("telegram_id"):
        rows.append([
            InlineKeyboardButton(text="✉️ Написати", url=f"tg://user?id={car['telegram_id']}")
        ])

    if not any([car.get("phone"), car.get("website"), car.get("username"), car.get("telegram_id")]):
        rows.append([
            InlineKeyboardButton(text="⚠️ Контакт відсутній", callback_data="noop")
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)
