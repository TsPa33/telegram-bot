from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_card_keyboard(car: dict, page: int, total: int):
    rows = []

    car_id = car.get("id")

    if not car_id:
        return InlineKeyboardMarkup(inline_keyboard=[])

    # ================= CONTACT BLOCK =================

    contact_row = []

    if car.get("phone"):
        contact_row.append(
            InlineKeyboardButton(
                text="📞 Подзвонити",
                callback_data=f"phone:{car_id}"
            )
        )

    if car.get("username"):
        username = car.get("username", "").replace("@", "")
        contact_row.append(
            InlineKeyboardButton(
                text="💬 Написати",
                url=f"https://t.me/{username}"
            )
        )
    elif car.get("telegram_id"):
        contact_row.append(
            InlineKeyboardButton(
                text="💬 Написати",
                url=f"tg://user?id={car['telegram_id']}"
            )
        )

    if contact_row:
        rows.append(contact_row)

    # ================= SITE (FIXED) =================

    if car.get("website"):
        url = car.get("website")

        if url and not url.startswith("http"):
            url = "https://" + url

        rows.append([
            InlineKeyboardButton(
                text="🌐 Відкрити сайт",
                url=url
            )
        ])

    # ================= FALLBACK =================

    if not any([
        car.get("phone"),
        car.get("website"),
        car.get("username"),
        car.get("telegram_id")
    ]):
        rows.append([
            InlineKeyboardButton(
                text="⚠️ Контакт відсутній",
                callback_data="noop"
            )
        ])

    # ================= PAGINATION =================

    if total > 1:
        nav_row = []

        if page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=f"page:{page - 1}"
                )
            )

        nav_row.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total}",
                callback_data="noop"
            )
        )

        if page < total - 1:
            nav_row.append(
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=f"page:{page + 1}"
                )
            )

        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)
