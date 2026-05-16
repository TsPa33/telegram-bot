import logging
import os
from html import escape

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.database.repositories.model_repo import get_brands_with_ids
from bot.keyboards.brands import brand_kb
from bot.keyboards.buyer_home import buyer_home_kb
from bot.keyboards.buyer_reply import buyer_reply_kb
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


def _compact_result_text(item: dict, item_type: str) -> str:
    if item_type == "service":
        title = item.get("title") or item.get("category") or "Автопослуга"
        vehicle = item.get("category") or "CarPot Service"
        price = item.get("price") or "уточнюйте"
    elif item_type == "seller":
        title = item.get("description") or "Продавець може мати потрібну пропозицію"
        vehicle = "Продавець CarPot"
        price = "уточнюйте"
    else:
        brand_model = " ".join(part for part in [item.get("brand"), item.get("model")] if part)
        title = item.get("description") or "Авто на розборці / запчастини"
        vehicle = brand_model or "CarPot Marketplace"
        price = item.get("price") or "уточнюйте"

    seller = item.get("shop_name") or item.get("name") or item.get("username") or "Продавець CarPot"
    city = item.get("city") or "Україна"

    return (
        f"🚘 <b>{escape(str(vehicle))}</b>\n\n"
        f"{escape(str(title))[:180]}\n"
        f"💰 {escape(str(price))}\n\n"
        f"🏪 {escape(str(seller))}\n"
        f"📍 {escape(str(city))}"
    )


def _compact_result_kb(item: dict, item_type: str) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text="Детальніше", callback_data="buyer_ai:details")]
    username = (item.get("username") or "").strip() if isinstance(item.get("username"), str) else ""
    if username:
        row.append(InlineKeyboardButton(text="Запитати", url=f"https://t.me/{username.lstrip('@')}"))
    else:
        row.append(InlineKeyboardButton(text="Запитати", callback_data="buyer_ai:ask"))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text="Створити заявку", callback_data="buyer_ai:create_request")],
        ]
    )


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

    await message.answer("🔎 Шукаю в CarPot Marketplace...")

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

    items: list[tuple[dict, str]] = []
    items.extend((_record_to_dict(item), "car") for item in (results.get("cars") or [])[:3])
    if len(items) < 3:
        items.extend((_record_to_dict(item), "service") for item in (results.get("services") or [])[: 3 - len(items)])
    if len(items) < 3:
        items.extend((_record_to_dict(item), "seller") for item in (results.get("sellers") or [])[: 3 - len(items)])

    await state.clear()

    if not items:
        await message.answer(
            "😕 Точних результатів поки не знайшли.\n\nСтворіть заявку — CarPot передасть її релевантним продавцям.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Створити заявку", callback_data="buyer_ai:create_request")]]
            ),
        )
        return

    await message.answer(f"✅ Знайшли {len(items)} релевантні результати:")
    for item, item_type in items:
        await message.answer(
            _compact_result_text(item, item_type),
            parse_mode="HTML",
            reply_markup=_compact_result_kb(item, item_type),
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
