from __future__ import annotations

from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _valid_website_url(item: dict[str, Any]) -> str | None:
    url = _clean(item.get("website_url") or item.get("website"))
    if url.startswith("https://"):
        return url
    if url.startswith("http://"):
        return "https://" + url[len("http://"): ]
    return None


def _clean(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _short(value: Any, limit: int = 220, default: str = "") -> str:
    text = _clean(value, default)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _seller_name(item: dict[str, Any]) -> str:
    return _clean(item.get("shop_name") or item.get("name") or item.get("username"), "Продавець")


def _city(item: dict[str, Any]) -> str:
    return _clean(item.get("city"), "—")


def _vehicle_label(item: dict[str, Any]) -> str:
    return _clean(" ".join(x for x in [_clean(item.get("brand")), _clean(item.get("model"))] if x), "Авто на розборі")


def _contact_lines(item: dict[str, Any]) -> list[str]:
    lines = []
    phone = _clean(item.get("phone"))
    username = _clean(item.get("telegram_username") or item.get("telegram") or item.get("username")).lstrip("@")
    if phone:
        lines.append(f"Телефон: {escape(phone)}")
    if username:
        lines.append(f"Telegram: @{escape(username)}")
    return lines


def format_search_card(item: dict[str, Any], item_type: str) -> str:
    lines = [f"<b>{escape(_vehicle_label(item))}</b>"]
    part_name = _clean(item.get("part_name") or item.get("description"))
    if item_type == "car" or not part_name:
        lines.extend(["Є авто на розборі", ""])
    else:
        price = _clean(item.get("part_price") or item.get("price"), "уточнюйте")
        lines.extend([f"Запчастина: {escape(_short(part_name, 100))}", f"Ціна: {escape(price)} грн", ""])

    lines.extend([f"Продавець: {escape(_seller_name(item))}", f"Місто: {escape(_city(item))}"])
    lines.extend(_contact_lines(item))
    additional = int(item.get("additional_matches") or 0)
    if additional > 0:
        lines.extend(["", f"Додатково знайдено: {additional} позицій"])
    return "\n".join(lines)


def _contact_button(item: dict[str, Any], text: str, fallback_callback: str) -> InlineKeyboardButton:
    username = _clean(item.get("telegram_username") or item.get("telegram") or item.get("username"))
    if username:
        return InlineKeyboardButton(text=text, url=f"https://t.me/{username.lstrip('@')}")
    return InlineKeyboardButton(text=text, callback_data=fallback_callback)


def search_result_kb(item: dict[str, Any], item_type: str, page: int, total: int) -> InlineKeyboardMarkup:
    item_id = _clean(item.get("id") or item.get("part_id") or item.get("car_id"), "0")
    rows = [
        [_contact_button(item, "Зв'язатись з продавцем", f"buyer_search:ask:{item_type}:{item_id}")],
        [InlineKeyboardButton(text="Створити заявку", callback_data=f"buyer_search:create_request:{item_type}:{item_id}")],
    ]

    site_url = _valid_website_url(item)
    if site_url:
        rows.append([InlineKeyboardButton(text="Сайт продавця", url=site_url)])

    if total > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="← Попередній", callback_data=f"buyer_search:prev:{page - 1}"))
        nav_row.append(InlineKeyboardButton(text=f"{page}/{total}", callback_data="buyer_search:noop"))
        if page < total:
            nav_row.append(InlineKeyboardButton(text="Наступний →", callback_data=f"buyer_search:next:{page + 1}"))
        rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_search_details(item: dict[str, Any], item_type: str) -> str:
    return format_search_card(item, item_type)


def no_results_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Створити заявку", callback_data="buyer_search:create_request:fallback:0")]])


def request_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Підтвердити", callback_data="buyer_request:confirm")]])


def request_created_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Мої заявки", callback_data="buyer:requests")]])
