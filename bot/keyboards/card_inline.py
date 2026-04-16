from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re


def is_valid_url(url: str) -> bool:
    if not url:
        return False

    if re.search(r"[а-яА-Я ]", url):
        return False

    if "." not in url:
        return False

    return True


def normalize_url(url: str) -> str | None:
    if not url:
        return None

    url = url.strip()

    if not url:
        return None

    if not url.startswith("http"):
        url = "https://" + url

    if not is_valid_url(url):
        return None

    return url


def build_card_keyboard(car: dict, page: int | None = None, total: int | None = None):
    rows = []
    car_id = car.get("id")

    # ================= CONTACT =================

    contact_row = []

    if car.get("phone"):
        contact_row.append(
            InlineKeyboardButton(
                text="📞 Подзвонити",
                callback_data=f"phone:{car_id}"
            )
        )

    if car.get("username"):
        contact_row.append(
            InlineKeyboardButton(
                text="💬 Написати",
                url=f"https://t.me/{car['username']}"
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

    # ================= SITE =================

    normalized_url = normalize_url(car.get("website"))

    if normalized_url:
        rows.append([
            InlineKeyboardButton(
                text="🌐 Відкрити сайт",
                url=normalized_url
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="⚠️ Некоректний сайт",
                callback_data="noop"
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

    if page is not None and total is not None and total > 1:
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
