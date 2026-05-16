import logging
import os
from collections.abc import Mapping
from html import escape
from datetime import date, datetime

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.database.repositories.model_repo import get_brands_with_ids
from bot.keyboards.brands import brand_kb
from bot.keyboards.buyer_home import buyer_home_kb
from bot.keyboards.buyer_reply import buyer_reply_kb
from bot.keyboards.buyer_search_inline import (
    format_search_card,
    no_results_kb,
    request_confirm_kb,
    request_created_kb,
    search_result_kb,
)
from bot.states.buyer_states import Buyer, BuyerStates
from bot.services.ai_request_interpreter import interpret_buyer_request
from bot.services.marketplace_search import run_priority_marketplace_search
from bot.services.buyer_request_service import (
    BuyerRequestInput,
    BuyerRequestValidationError,
    submit_marketplace_buyer_request,
)

from bot.keyboards.main_menu import main_menu_kb

router = Router()
logger = logging.getLogger(__name__)


# ================= BUYER HOME =================

BUYER_HOME_TEXT = "🔎 CarPot Search\n\nОпишіть, що потрібно знайти — або відкрийте свої заявки."
BUYER_HOME_IMAGE_URL = os.getenv("BUYER_HOME_IMAGE_URL")

SEARCH_PROMPT_TEXT = (
    "🔎 CarPot Search\n\n"
    "Опишіть, що потрібно знайти:\n"
    "запчастину, авто на розборці або автопослугу.\n\n"
    "Приклади:\n"
    "• фара Audi A6 C7\n"
    "• АКПП BMW F10\n"
    "• автоелектрик Львів"
)


def _record_to_dict(record) -> dict:
    if isinstance(record, dict):
        return record
    if hasattr(record, "items"):
        return dict(record)
    return {}


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Mapping) or hasattr(value, "items"):
        return {str(key): _json_safe(item) for key, item in dict(value).items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    return str(value)


def _ai_search_query(interpretation: dict, raw_query: str) -> str:
    terms = [
        interpretation.get("part_name"),
        interpretation.get("service_type"),
        interpretation.get("brand"),
        interpretation.get("model"),
        interpretation.get("generation"),
        interpretation.get("engine"),
    ]

    compact_terms = [
        str(term).strip()
        for term in terms
        if str(term or "").strip()
    ]

    if compact_terms:
        return " ".join(dict.fromkeys(compact_terms))[:240]

    search_terms = interpretation.get("search_terms") or []

    if isinstance(search_terms, list) and search_terms:
        return " ".join(
            str(term).strip()
            for term in search_terms
            if str(term or "").strip()
        )[:240]

    return (interpretation.get("normalized_query") or raw_query or "")[:240]


def _compact_search_item(item, item_type: str) -> dict:
    payload = _record_to_dict(item)

    allowed_keys = {
        "id",
        "seller_id",
        "brand",
        "model",
        "donor_generation",
        "description",
        "price",
        "shop_name",
        "name",
        "username",
        "city",
        "website",
        "compatibility_notes",
        "category",
        "title",
        "address",
        "cars_count",
        "services_count",
    }

    compact = {
        key: payload.get(key)
        for key in allowed_keys
        if key in payload
    }

    compact["_type"] = item_type
    return _json_safe(compact)


def _collect_search_items(results: dict) -> list[dict]:
    items: list[dict] = []

    for item in (results.get("cars") or [])[:6]:
        items.append(_compact_search_item(item, "car"))

    for item in (results.get("services") or [])[:6]:
        items.append(_compact_search_item(item, "service"))

    for item in (results.get("sellers") or [])[:6]:
        items.append(_compact_search_item(item, "seller"))

    return items[:9]


def _search_session_payload(items: list[dict], raw_query: str, interpretation: dict) -> dict:
    compact_interpretation = {
        "brand": interpretation.get("brand") or "",
        "model": interpretation.get("model") or interpretation.get("generation") or "",
        "part_name": interpretation.get("part_name") or "",
        "service_type": interpretation.get("service_type") or "",
        "city": interpretation.get("city") or "",
        "category": interpretation.get("category") or "",
    }

    return {
        "buyer_search_items": _json_safe(items),
        "buyer_search_page": 1,
        "buyer_search_query": _json_safe(raw_query),
        "buyer_search_interpretation": _json_safe(compact_interpretation),
        "buyer_request_item": _json_safe(items[0]) if items else None,
    }


def _clean_text(value, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _buyer_search_item(data: dict, item_type: str, item_id: str) -> dict | None:
    for item in data.get("buyer_search_items") or []:
        if item.get("_type") == item_type and str(item.get("id") or "0") == str(item_id):
            return item
    return None


def _current_buyer_search_item(data: dict) -> dict | None:
    item = data.get("buyer_request_item")
    if isinstance(item, dict):
        return item

    items = data.get("buyer_search_items") or []
    if not items:
        return None

    page = int(data.get("buyer_search_page") or 1)
    index = max(0, min(page - 1, len(items) - 1))
    return items[index]


def _request_type_and_category(item: dict | None, interpretation: dict) -> tuple[str, str]:
    item_type = (item or {}).get("_type")
    category = _clean_text(interpretation.get("category"))

    if item_type == "service" or category == "service":
        return "service", "service"

    if item_type == "seller":
        return "part", "parts"

    if category in {"cars", "car"}:
        return "car", "cars"

    if category in {"diagnostics", "tow", "tires", "other"}:
        return category if category != "tires" else "other", category

    return "part", "parts"


def _request_description(data: dict, item: dict | None) -> str:
    raw_query = _clean_text(data.get("buyer_search_query"))
    interpretation = data.get("buyer_search_interpretation") or {}
    details = []

    if raw_query:
        details.append(f"Запит: {raw_query}")

    part_or_service = _clean_text(interpretation.get("part_name") or interpretation.get("service_type"))
    vehicle = " ".join(
        value for value in [
            _clean_text(interpretation.get("brand")),
            _clean_text(interpretation.get("model")),
        ] if value
    )
    if part_or_service:
        details.append(f"Потрібно: {part_or_service}")
    if vehicle:
        details.append(f"Авто: {vehicle}")

    if item:
        item_title = _clean_text(
            item.get("description") or item.get("title") or item.get("shop_name") or item.get("name")
        )
        if item_title:
            details.append(f"Результат пошуку: {item_title[:240]}")

    description = "\n".join(details).strip()
    if len(description) >= 12:
        return description[:1400]

    return "Покупець створив заявку з Telegram-пошуку CarPot"


def _request_summary(data: dict) -> str:
    interpretation = data.get("buyer_search_interpretation") or {}
    item = _current_buyer_search_item(data)
    request_type, category = _request_type_and_category(item, interpretation)

    labels = {
        "part": "запчастина",
        "car": "авто",
        "service": "послуга",
        "diagnostics": "діагностика",
        "tow": "евакуатор",
        "other": "інше",
    }

    lines = [
        "📝 <b>Підтвердіть заявку</b>",
        "",
        f"Тип: {escape(labels.get(request_type, request_type))}",
        f"Категорія: {escape(category)}",
    ]

    brand = _clean_text(interpretation.get("brand"))
    model = _clean_text(interpretation.get("model"))
    if brand or model:
        lines.append(f"Авто: {escape(' '.join(value for value in [brand, model] if value))}")

    part_or_service = _clean_text(interpretation.get("part_name") or interpretation.get("service_type"))
    if part_or_service:
        lines.append(f"Потрібно: {escape(part_or_service)}")

    lines.extend([
        f"Місто: {escape(_clean_text(data.get('buyer_request_city'), '—'))}",
        f"Телефон: {escape(_clean_text(data.get('buyer_request_phone'), '—'))}",
        "",
        escape(_request_description(data, item)),
    ])
    return "\n".join(lines)


def _buyer_telegram_username(user: types.User) -> str | None:
    if user.username:
        return f"@{user.username}"
    return None


async def show_buyer_home(message: types.Message, state: FSMContext):
    await state.clear()

    if BUYER_HOME_IMAGE_URL:
        try:
            await message.answer_photo(
                photo=BUYER_HOME_IMAGE_URL,
                caption=BUYER_HOME_TEXT,
                reply_markup=buyer_home_kb(),
            )
        except TelegramBadRequest as exc:
            logger.warning("Buyer home image unavailable: %s", exc)
            await message.answer(
                BUYER_HOME_TEXT,
                reply_markup=buyer_home_kb(),
            )
    else:
        await message.answer(
            BUYER_HOME_TEXT,
            reply_markup=buyer_home_kb(),
        )

    await message.answer(
        "Швидкий доступ до меню:",
        reply_markup=buyer_reply_kb(),
    )


# ================= ROLE ENTRY =================

@router.callback_query(F.data == "role:buyer")
async def enter_buyer(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_buyer_home(callback.message, state)


# ================= NAV =================

@router.callback_query(F.data == "nav:home")
async def buyer_home_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_buyer_home(callback.message, state)


@router.callback_query(F.data == "nav:main")
async def buyer_main_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "🔁 Головне меню\n\nОбери дію:",
        reply_markup=await main_menu_kb(callback.from_user.id),
    )


# ================= BUYER ACTIONS =================

@router.callback_query(F.data == "buyer:find")
async def buyer_find_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(BuyerStates.waiting_for_search_query)
    await callback.message.answer(
        SEARCH_PROMPT_TEXT,
        reply_markup=buyer_reply_kb(),
    )


@router.callback_query(F.data == "buyer:history")
async def buyer_history_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Історія пошуку буде доступна незабаром.")


@router.callback_query(F.data == "buyer_ai:details")
async def buyer_ai_details(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Детальний перегляд у Telegram буде доступний незабаром. "
        "Для уточнення натисніть «Запитати» або створіть заявку."
    )


@router.callback_query(F.data == "buyer_ai:ask")
async def buyer_ai_ask(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Контакт продавця недоступний у цьому результаті. "
        "Створіть заявку — CarPot передасть її релевантним продавцям."
    )


@router.callback_query(F.data == "buyer_ai:create_request")
async def buyer_ai_create_request(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Створення заявки з AI-пошуку буде доступне незабаром. "
        "Поки що відкрийте «📋 Мої заявки» або напишіть запит у підтримку."
    )



@router.callback_query(F.data.startswith("buyer_search:create_request:"))
async def buyer_search_create_marketplace_request(callback: types.CallbackQuery, state: FSMContext):
    parts = (callback.data or "").split(":")
    item_type = parts[2] if len(parts) > 2 else "fallback"
    item_id = parts[3] if len(parts) > 3 else "0"

    data = await state.get_data()
    item = _buyer_search_item(data, item_type, item_id) if item_type != "fallback" else _current_buyer_search_item(data)
    interpretation = data.get("buyer_search_interpretation") or {}
    city = _clean_text(interpretation.get("city"))

    await state.update_data(
        buyer_request_item=_json_safe(item) if item else None,
        buyer_request_city=city,
        buyer_request_phone=None,
    )

    await callback.answer()

    if not city:
        await state.set_state(BuyerStates.request_city)
        await callback.message.answer(
            "У якому місті актуальна заявка?\n\nНаприклад: Київ, Львів, Дніпро"
        )
        return

    await state.set_state(BuyerStates.request_phone)
    await callback.message.answer(
        "Вкажіть телефон для звʼязку з продавцями.\n\nНаприклад: +380671234567"
    )


@router.message(BuyerStates.request_city, F.text)
async def buyer_request_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if len(city) < 2:
        await message.answer("Вкажіть місто, наприклад: Київ")
        return

    await state.update_data(buyer_request_city=_json_safe(city))
    await state.set_state(BuyerStates.request_phone)
    await message.answer(
        "Вкажіть телефон для звʼязку з продавцями.\n\nНаприклад: +380671234567"
    )


@router.message(BuyerStates.request_phone, F.text)
async def buyer_request_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if len(phone) < 9:
        await message.answer("Вкажіть коректний телефон, наприклад: +380671234567")
        return

    await state.update_data(buyer_request_phone=_json_safe(phone))
    await state.set_state(BuyerStates.request_confirm)
    data = await state.get_data()
    await message.answer(
        _request_summary(data),
        parse_mode="HTML",
        reply_markup=request_confirm_kb(),
    )


@router.callback_query(BuyerStates.request_confirm, F.data == "buyer_request:confirm")
async def buyer_request_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    interpretation = data.get("buyer_search_interpretation") or {}
    item = _current_buyer_search_item(data)
    request_type, category = _request_type_and_category(item, interpretation)

    payload = BuyerRequestInput(
        buyer_name=callback.from_user.full_name,
        buyer_phone=data.get("buyer_request_phone"),
        buyer_telegram=_buyer_telegram_username(callback.from_user),
        city=data.get("buyer_request_city") or interpretation.get("city"),
        request_type=request_type,
        category=category,
        brand=_clean_text(interpretation.get("brand")) or None,
        model=_clean_text(interpretation.get("model")) or None,
        vin=None,
        description=_request_description(data, item),
        urgency="soon",
        photos=None,
    )

    await callback.answer()

    try:
        await submit_marketplace_buyer_request(payload)
    except BuyerRequestValidationError as exc:
        await callback.message.answer(str(exc))
        if "місто" in str(exc).lower():
            await state.set_state(BuyerStates.request_city)
        elif "телефон" in str(exc).lower():
            await state.set_state(BuyerStates.request_phone)
        return
    except Exception as exc:
        logger.exception("Telegram marketplace buyer request creation failed: %s", exc)
        await callback.message.answer(
            "⚠️ Не вдалося створити заявку зараз. Спробуйте ще раз або зверніться в підтримку."
        )
        return

    await state.clear()
    await callback.message.answer(
        "✅ Заявку створено.\n"
        "Продавці отримають запит і зможуть запропонувати варіанти.",
        reply_markup=request_created_kb(),
    )


# ================= MODERN SEARCH FLOW =================

@router.message(BuyerStates.waiting_for_search_query, F.text)
async def handle_buyer_ai_search_query(message: Message, state: FSMContext):
    raw_query = (message.text or "").strip()

    if len(raw_query) < 3:
        await message.answer(
            "Опишіть запит трохи детальніше, наприклад: фара Audi A6 C7"
        )
        return

    await message.answer("🔎 Шукаю в CarPot...")

    try:
        interpretation = await interpret_buyer_request(raw_query)

        search_query = _ai_search_query(interpretation, raw_query)

        results = await run_priority_marketplace_search(
            interpretation=interpretation,
            raw_query=raw_query,
            search_query=search_query,
            limit=3,
        )

    except Exception as exc:
        logger.exception("Telegram buyer AI search failed: %s", exc)
        await state.clear()
        await message.answer(
            "⚠️ Не вдалося виконати пошук зараз. "
            "Спробуйте ще раз або зверніться в підтримку.",
            reply_markup=buyer_home_kb(),
        )
        return

    items = _collect_search_items(results)

    await state.clear()
    await state.update_data(
        **_search_session_payload(items, raw_query, interpretation)
    )

    if not items:
        await message.answer(
            "❌ Точного результату поки немає.\n\n"
            "Створіть заявку — продавці отримають ваш запит і зможуть запропонувати варіанти.",
            reply_markup=no_results_kb(),
        )
        return

    first_item = items[0]
    item_type = first_item.get("_type", "car")

    await message.answer(
        format_search_card(first_item, item_type),
        parse_mode="HTML",
        reply_markup=search_result_kb(
            first_item,
            item_type,
            page=1,
            total=len(items),
        ),
    )


# ================= LEGACY SEARCH FLOW =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()

    brands = await get_brands_with_ids()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    await state.set_state(Buyer.brand)

    await message.answer(
        "🔎 Переходимо до пошуку...",
        reply_markup=buyer_reply_kb(),
    )

    await message.answer(
        "🚗 Обери бренд",
        reply_markup=brand_kb(brands),
    )