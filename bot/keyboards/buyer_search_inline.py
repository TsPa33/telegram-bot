from __future__ import annotations

from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


SEARCH_PAGE_SIZE = 1
MAX_CARD_TEXT = 180
MAX_DETAIL_TEXT = 520


def _clean(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _short(value: Any, limit: int = MAX_CARD_TEXT, default: str = "") -> str:
    text = _clean(value, default)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _price(value: Any) -> str:
    text = _clean(value)
    if not text:
        return "уточнюйте"
    if any(symbol in text for symbol in ("$", "€", "₴")):
        return text
    return text


def _seller_name(item: dict[str, Any]) -> str:
    return _clean(
        item.get("shop_name") or item.get("name") or item.get("username"),
        "Продавець CarPot",
    )


def _city(item: dict[str, Any]) -> str:
    return _clean(item.get("city"), "Україна")


def _vehicle_label(item: dict[str, Any]) -> str:
    parts = [item.get("brand"), item.get("model"), item.get("donor_generation")]
    return _clean(" ".join(_clean(part) for part in parts if _clean(part)), "Авто / запчастини")


def _service_lines(item: dict[str, Any]) -> tuple[str, str]:
    title = _clean(item.get("title") or item.get("category"), "Автопослуга")
    description = _short(item.get("description"), 110, "Опис уточнюйте у виконавця")
    return title, description


def _seller_specialization(item: dict[str, Any]) -> str:
    description = _short(item.get("description"), 120)
    if description:
        return description

    counters = []
    if item.get("cars_count"):
        counters.append("авто / запчастини")
    if item.get("services_count"):
        counters.append("послуги")
    return " / ".join(counters) or "Автозапчастини / сервіс"


def _contact_lines(item: dict[str, Any]) -> list[str]:
    lines = []
    phone = _clean(item.get("phone"))
    username = _clean(item.get("telegram_username") or item.get("telegram") or item.get("username")).lstrip("@")
    website = _clean(item.get("website"))

    if phone:
        lines.append(f"📞 {escape(phone)}")
    if username:
        lines.append(f"💬 @{escape(username)}")
    if website:
        lines.append(f"🌐 {escape(website)}")
    return lines


def _photo_line(item: dict[str, Any]) -> str | None:
    if item.get("photo") or item.get("photo_id") or item.get("file_id"):
        return "📷 Є фото"
    return None


def format_search_card(item: dict[str, Any], item_type: str) -> str:
    if item_type == "service":
        title, description = _service_lines(item)
        lines = [f"🔧 <b>{escape(title)}</b>", "", escape(description), "", f"📍 {escape(_city(item))}"]
        photo_line = _photo_line(item)
        if photo_line:
            lines.append(photo_line)
        return "\n".join(lines)

    if item_type == "seller":
        lines = [
            f"🏪 <b>{escape(_seller_name(item))}</b>",
            "",
            "Спеціалізація:",
            escape(_seller_specialization(item)),
            "",
            f"📍 {escape(_city(item))}",
        ]
        lines.extend(_contact_lines(item))
        photo_line = _photo_line(item)
        if photo_line:
            lines.append(photo_line)
        return "\n".join(lines)

    title = _short(item.get("description"), 120, "Авто на розборці / запчастини")
    lines = [
        f"🚘 <b>{escape(_vehicle_label(item))}</b>",
        "",
        escape(title),
        f"💰 {escape(_price(item.get('price')))}",
        "",
        f"🏪 {escape(_seller_name(item))}",
        f"📍 {escape(_city(item))}",
    ]
    lines.extend(_contact_lines(item))
    photo_line = _photo_line(item)
    if photo_line:
        lines.append(photo_line)
    return "\n".join(lines)


def format_search_details(item: dict[str, Any], item_type: str) -> str:
    if item_type == "service":
        title, description = _service_lines(item)
        address = _clean(item.get("address"))
        seller = _seller_name(item)
        lines = [
            f"🔧 <b>{escape(title)}</b>",
            "",
            escape(_short(description, MAX_DETAIL_TEXT)),
            "",
            f"🏪 {escape(seller)}",
            f"📍 {escape(_city(item))}",
        ]
        if address:
            lines.append(f"Адреса: {escape(address)}")
        if item.get("price"):
            lines.append(f"💰 {escape(_price(item.get('price')))}")
        lines.extend(_contact_lines(item))
        photo_line = _photo_line(item)
        if photo_line:
            lines.append(photo_line)
        return "\n".join(lines)

    if item_type == "seller":
        lines = [
            f"🏪 <b>{escape(_seller_name(item))}</b>",
            "",
            "Спеціалізація:",
            escape(_seller_specialization(item)),
            "",
            f"📍 {escape(_city(item))}",
        ]
        lines.extend(_contact_lines(item))
        photo_line = _photo_line(item)
        if photo_line:
            lines.append(photo_line)
        return "\n".join(lines)

    details = _short(item.get("description"), MAX_DETAIL_TEXT, "Авто на розборці / запчастини")
    notes = _clean(item.get("compatibility_notes"))
    lines = [
        f"🚘 <b>{escape(_vehicle_label(item))}</b>",
        "",
        escape(details),
    ]
    if notes:
        lines.extend(["", f"Сумісність: {escape(_short(notes, 220))}"])
    lines.extend([
        "",
        f"💰 {escape(_price(item.get('price')))}",
        f"🏪 {escape(_seller_name(item))}",
        f"📍 {escape(_city(item))}",
    ])
    lines.extend(_contact_lines(item))
    photo_line = _photo_line(item)
    if photo_line:
        lines.append(photo_line)
    return "\n".join(lines)


def _contact_button(item: dict[str, Any], text: str, fallback_callback: str) -> InlineKeyboardButton:
    username = _clean(item.get("telegram_username") or item.get("telegram") or item.get("username"))
    if username:
        return InlineKeyboardButton(text=text, url=f"https://t.me/{username.lstrip('@')}")
    return InlineKeyboardButton(text=text, callback_data=fallback_callback)


def search_result_kb(item: dict[str, Any], item_type: str, page: int, total: int) -> InlineKeyboardMarkup:
    item_id = _clean(item.get("id"), "0")
    ask_text = "Написати" if item_type in {"seller", "service"} else "Запитати"
    rows = [
        [InlineKeyboardButton(text="Детальніше", callback_data=f"buyer_search:details:{item_type}:{item_id}")],
        [_contact_button(item, ask_text, f"buyer_search:ask:{item_type}:{item_id}")],
    ]

    rows.append([InlineKeyboardButton(text="Створити заявку", callback_data=f"buyer_search:create_request:{item_type}:{item_id}")])

    if total > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="‹", callback_data=f"buyer_search:prev:{page - 1}"))
        nav_row.append(InlineKeyboardButton(text=f"{page}/{total}", callback_data="buyer_search:noop"))
        if page < total:
            nav_row.append(InlineKeyboardButton(text="›", callback_data=f"buyer_search:next:{page + 1}"))
        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def no_results_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Створити заявку", callback_data="buyer_search:create_request:fallback:0")],
            [InlineKeyboardButton(text="Мої заявки", callback_data="buyer:requests")],
        ]
    )


def request_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Підтвердити", callback_data="buyer_request:confirm")],
            [InlineKeyboardButton(text="✏️ Редагувати", callback_data="buyer_request:edit")],
            [InlineKeyboardButton(text="🔎 Новий пошук", callback_data="buyer:find")],
        ]
    )


def request_created_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мої заявки", callback_data="buyer:requests")],
            [InlineKeyboardButton(text="🔎 Новий пошук", callback_data="buyer:find")],
        ]
    )
