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


def build_card_keyboard(
    car: dict,
    page: int | None = None,
    total: int | None = None,
    is_car_favorite: bool = False,
    is_seller_favorite: bool = False,
    is_website_favorite: bool = False,
):
    rows = []
    car_id = car.get("id")

    # ================= CRM ACTIONS =================

    rows.append([
        InlineKeyboardButton(
            text="💔 Прибрати авто" if is_car_favorite else "❤️ Зберегти авто",
            callback_data=f"fav:toggle:car:{car_id}",
        )
    ])

    if car.get("seller_id"):
        rows.append([
            InlineKeyboardButton(
                text="💔 Прибрати продавця" if is_seller_favorite else "🏪 Зберегти продавця",
                callback_data=f"fav:toggle:seller:{car['seller_id']}",
            )
        ])

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
        rows.append([
            InlineKeyboardButton(
                text="💔 Прибрати сайт" if is_website_favorite else "❤️ Зберегти сайт",
                callback_data=f"fav:toggle:website:{car_id}",
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

        # ⬅️ prev
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data="prev"
                )
            )

        # center
        nav_row.append(
            InlineKeyboardButton(
                text=f"{page}/{total}",
                callback_data="noop"
            )
        )

        # ➡️ next
        if page < total:
            nav_row.append(
                InlineKeyboardButton(
                    text="➡️",
                    callback_data="next"
                )
            )

        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)
