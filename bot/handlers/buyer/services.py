import logging
import math
from urllib.parse import quote_plus

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database.repositories.service_repo import (
    get_services_by_filter,
    get_all_cities,
    increment_calls,
    increment_clicks,
    increment_views,
)
from bot.database.repositories.buyer_repo import (
    add_history,
    create_buyer_request,
    is_favorite,
    toggle_favorite,
)
from bot.states.service_states import ServiceStates

router = Router()
logger = logging.getLogger(__name__)

SERVICE_CATEGORIES = [
    "СТО",
    "Детейлінг",
    "Евакуатор",
    "Шиномонтаж",
    "Автоелектрик",
]

LIMIT = 1


# ================= KEYBOARDS =================

def service_city_kb(cities):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=c["city"], callback_data=f"svc_city:{c['city']}")]
            for c in cities
        ]
    )


def service_category_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cat, callback_data=f"svc_category:{cat}")]
            for cat in SERVICE_CATEGORIES
        ]
    )


# ================= HELPERS =================

def normalize_website(url):
    if not url:
        return None
    url = url.strip()
    if url.startswith("http"):
        return url
    return f"https://{url}"


def format_service(service):
    return (
        f"🔧 {service['title']}\n"
        f"📍 {service['city']}\n"
        f"📌 {service['address']}\n\n"
        f"{service.get('description') or 'Опис відсутній'}"
    )


async def build_kb(service, page, total, telegram_id: int):
    route = f"https://www.google.com/maps/search/?api=1&query={quote_plus(service['address'])}"

    service_favorite = await is_favorite(telegram_id, "service", str(service["id"]))
    website_favorite = await is_favorite(telegram_id, "website", normalize_website(service.get("website")) or str(service["id"]))

    rows = [
        [InlineKeyboardButton(
            text="💔 Прибрати послугу" if service_favorite else "❤️ Зберегти послугу",
            callback_data=f"fav:toggle:service:{service['id']}",
        )],
        [InlineKeyboardButton(text="📞 Подзвонити", callback_data=f"svc_call:{service['id']}")],
        [InlineKeyboardButton(text="🌐 Сайт", callback_data=f"svc_site:{service['id']}")],
        [InlineKeyboardButton(
            text="💔 Прибрати сайт" if website_favorite else "❤️ Зберегти сайт",
            callback_data=f"fav:toggle:website_svc:{service['id']}",
        )],
        [InlineKeyboardButton(text="📍 Маршрут", url=route)],
    ]

    if total > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data="svc_prev"))
        nav.append(InlineKeyboardButton(text=f"{page}/{total}", callback_data="noop"))
        if page < total:
            nav.append(InlineKeyboardButton(text="➡️", callback_data="svc_next"))
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ================= CARD =================

async def send_card(message: Message, state: FSMContext, new=False, user_id: int | None = None):
    data = await state.get_data()

    items = data.get("items", [])
    page = data.get("page", 1)

    if not items:
        await message.answer("❌ Нічого не знайдено")
        await state.clear()
        return

    total = max(1, math.ceil(len(items) / LIMIT))
    start = (page - 1) * LIMIT

    service = items[start]

    viewer_id = user_id or message.chat.id
    await increment_views(service["id"])
    await add_history(viewer_id, "service", str(service["id"]))

    text = format_service(service)
    kb = await build_kb(service, page, total, viewer_id)

    if new:
        if service.get("photo_id"):
            try:
                await message.answer_photo(service["photo_id"], caption=text, reply_markup=kb)
            except TelegramBadRequest as exc:
                logger.warning("Service photo unavailable for service %s: %s", service.get("id"), exc)
                await message.answer(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        return

    try:
        await message.edit_text(text, reply_markup=kb)
    except:
        await message.answer(text, reply_markup=kb)


# ================= FLOW =================

@router.callback_query(F.data == "buyer:services")
async def start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(ServiceStates.city)
    await state.update_data(flow="buyer_services")

    cities = await get_all_cities()

    if not cities:
        await callback.message.answer("❌ Поки що немає послуг")
        return

    await callback.message.answer(
        "Оберіть місто:",
        reply_markup=service_city_kb(cities)
    )


@router.callback_query(ServiceStates.city, F.data.startswith("svc_city:"))
async def city(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if data.get("flow") != "buyer_services":
        return

    city = callback.data.split(":")[1]

    await state.update_data(city=city)
    await state.set_state(ServiceStates.category)

    await callback.message.answer("Оберіть категорію:", reply_markup=service_category_kb())


@router.callback_query(ServiceStates.category, F.data.startswith("svc_category:"))
async def category(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if data.get("flow") != "buyer_services":
        return

    category = callback.data.split(":")[1]

    services = await get_services_by_filter(data["city"], category)

    # 🔥 ФІКС datetime
    services_clean = []
    for s in services:
        item = dict(s)

        if item.get("created_at"):
            item["created_at"] = item["created_at"].isoformat()

        services_clean.append(item)

    services = services_clean

    if not services:
        await callback.message.answer("❌ Нічого не знайдено")
        await state.clear()
        return

    await state.update_data(items=services, page=1)

    await send_card(callback.message, state, new=True, user_id=callback.from_user.id)


# ================= NAV =================

@router.callback_query(ServiceStates.category, F.data == "svc_next")
async def next_page(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    if data.get("flow") != "buyer_services":
        return
    await state.update_data(page=data["page"] + 1)

    await send_card(callback.message, state, user_id=callback.from_user.id)


@router.callback_query(ServiceStates.category, F.data == "svc_prev")
async def prev_page(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    if data.get("flow") != "buyer_services":
        return
    await state.update_data(page=max(1, data["page"] - 1))

    await send_card(callback.message, state, user_id=callback.from_user.id)


# ================= ACTIONS =================

@router.callback_query(ServiceStates.category, F.data.startswith("svc_call:"))
async def call(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if data.get("flow") != "buyer_services":
        return

    service_id = int(callback.data.split(":")[1])
    await increment_calls(service_id)

    service = next((x for x in data.get("items", []) if x["id"] == service_id), None)

    await create_buyer_request(
        telegram_id=callback.from_user.id,
        request_type="service_phone",
        entity_type="service",
        entity_ref=str(service_id),
        seller_id=service.get("seller_id") if service else None,
        message="Buyer opened service phone",
    )

    await callback.message.answer(f"📞 {service.get('phone') if service else 'Не вказано'}")


@router.callback_query(ServiceStates.category, F.data.startswith("svc_site:"))
async def site(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if data.get("flow") != "buyer_services":
        return

    service_id = int(callback.data.split(":")[1])
    service = next((x for x in data.get("items", []) if x["id"] == service_id), None)

    if not service:
        return

    url = normalize_website(service.get("website"))

    if not url:
        await callback.message.answer("❌ Сайт не вказано")
        return

    await increment_clicks(service_id)
    await create_buyer_request(
        telegram_id=callback.from_user.id,
        request_type="service_site",
        entity_type="service",
        entity_ref=str(service_id),
        seller_id=service.get("seller_id"),
        message="Buyer opened service website",
    )

    await callback.message.answer(
        "🌐 Відкрити сайт",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Відкрити", url=url)]]
        ),
    )


@router.callback_query(ServiceStates.category, F.data.startswith("fav:toggle:website_svc:"))
async def toggle_service_website_favorite(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if data.get("flow") != "buyer_services":
        return

    service_id = int(callback.data.split(":")[-1])
    service = next((x for x in data.get("items", []) if x["id"] == service_id), None)
    if not service:
        return

    url = normalize_website(service.get("website"))
    if not url:
        await callback.message.answer("❌ Сайт не вказано")
        return

    is_added = await toggle_favorite(callback.from_user.id, "website", url)
    await callback.message.answer("Додано в обране" if is_added else "Прибрано з обраного")
