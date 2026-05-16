import logging
import os

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
    search_result_kb,
)
from bot.states.buyer_states import Buyer, BuyerStates
from bot.services.ai_request_interpreter import interpret_buyer_request
from bot.services.marketplace_search import run_priority_marketplace_search

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


def _ai_search_query(interpretation: dict, raw_query: str) -> str:
    terms = [
        interpretation.get("part_name"),
        interpretation.get("service_type"),
        interpretation.get("brand"),
        interpretation.get("model"),
        interpretation.get("generation"),
        interpretation.get("engine"),
    ]
    compact_terms = [str(term).strip() for term in terms if str(term or "").strip()]
    if compact_terms:
        return " ".join(dict.fromkeys(compact_terms))[:240]
    search_terms = interpretation.get("search_terms") or []
    if isinstance(search_terms, list) and search_terms:
        return " ".join(str(term).strip() for term in search_terms if str(term or "").strip())[:240]
    return (interpretation.get("normalized_query") or raw_query or "")[:240]


def _collect_search_items(results: dict) -> list[dict]:
    items: list[dict] = []
    for item in (results.get("cars") or [])[:6]:
        payload = _record_to_dict(item)
        payload["_type"] = "car"
        items.append(payload)
    for item in (results.get("services") or [])[:6]:
        payload = _record_to_dict(item)
        payload["_type"] = "service"
        items.append(payload)
    for item in (results.get("sellers") or [])[:6]:
        payload = _record_to_dict(item)
        payload["_type"] = "seller"
        items.append(payload)
    return items[:9]


def _search_session_payload(items: list[dict], raw_query: str, interpretation: dict) -> dict:
    return {
        "buyer_search_items": items,
        "buyer_search_page": 1,
        "buyer_search_query": raw_query,
        "buyer_search_interpretation": {
            "brand": interpretation.get("brand") or "",
            "model": interpretation.get("model") or interpretation.get("generation") or "",
            "part_name": interpretation.get("part_name") or "",
            "service_type": interpretation.get("service_type") or "",
            "city": interpretation.get("city") or "",
            "category": interpretation.get("category") or "",
        },
    }


async def show_buyer_home(message: types.Message, state: FSMContext):
    await state.clear()  # 🔥 гарантія чистого входу

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
        reply_markup=buyer_reply_kb()
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
    await callback.message.answer(SEARCH_PROMPT_TEXT, reply_markup=buyer_reply_kb())


@router.callback_query(F.data == "buyer:history")
async def buyer_history_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Історія пошуку буде доступна незабаром.")


@router.callback_query(F.data == "buyer_ai:details")
async def buyer_ai_details(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Детальний перегляд у Telegram буде доступний незабаром. Для уточнення натисніть «Запитати» або створіть заявку.")


@router.callback_query(F.data == "buyer_ai:ask")
async def buyer_ai_ask(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Контакт продавця недоступний у цьому результаті. Створіть заявку — CarPot передасть її релевантним продавцям.")


@router.callback_query(F.data == "buyer_ai:create_request")
async def buyer_ai_create_request(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Створення заявки з AI-пошуку буде доступне незабаром. Поки що відкрийте «📋 Мої заявки» або напишіть запит у підтримку.")


# ================= MODERN SEARCH FLOW =================

@router.message(BuyerStates.waiting_for_search_query, F.text)
async def handle_buyer_ai_search_query(message: Message, state: FSMContext):
    raw_query = (message.text or "").strip()
    if len(raw_query) < 3:
        await message.answer("Опишіть запит трохи детальніше, наприклад: фара Audi A6 C7")
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
            "⚠️ Не вдалося виконати пошук зараз. Спробуйте ще раз або зверніться в підтримку.",
            reply_markup=buyer_home_kb(),
        )
        return

    items = _collect_search_items(results)
    await state.clear()
    await state.update_data(**_search_session_payload(items, raw_query, interpretation))

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
        reply_markup=search_result_kb(first_item, item_type, page=1, total=len(items)),
    )


# ================= LEGACY SEARCH FLOW =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()  # 🔥 ізоляція flow

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
        reply_markup=brand_kb(brands)
    )
