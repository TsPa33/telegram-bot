import math
from urllib.parse import quote_plus

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message

from bot.database.repositories.service_repo import (
    get_services_by_filter,
    increment_calls,
    increment_clicks,
    increment_views,
)
from bot.states.service_states import ServiceStates

router = Router()

SERVICE_CATEGORIES = [
    "СТО",
    "Детейлінг",
    "Евакуатор",
    "Шиномонтаж",
    "Автоелектрик",
]

LIMIT = 1


def service_city_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Київ", callback_data="svc_city:Київ")],
            [InlineKeyboardButton(text="Львів", callback_data="svc_city:Львів")],
            [InlineKeyboardButton(text="Одеса", callback_data="svc_city:Одеса")],
        ]
    )


def service_category_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=category,
                    callback_data=f"svc_category:{category}",
                )
            ]
            for category in SERVICE_CATEGORIES
        ]
    )


def normalize_website(url: str | None) -> str | None:
    if not url:
        return None

    cleaned = url.strip()
    if not cleaned:
        return None

    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned

    return f"https://{cleaned}"


def build_service_card_kb(service: dict, page: int, total: int) -> InlineKeyboardMarkup:
    website = normalize_website(service.get("website"))
    route_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(service['address'])}"

    rows = [
        [InlineKeyboardButton(text="📞 Call", callback_data=f"svc_call:{service['id']}")],
        [
            InlineKeyboardButton(
                text="🌐 Website",
                callback_data=f"svc_site:{service['id']}",
            )
        ],
        [InlineKeyboardButton(text="📍 Route", url=route_url)],
    ]

    if not website:
        rows[1] = [InlineKeyboardButton(text="🌐 Website", callback_data="noop")]

    if total > 1:
        nav_row = []

        if page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️", callback_data="svc_prev"))

        nav_row.append(InlineKeyboardButton(text=f"{page}/{total}", callback_data="noop"))

        if page < total:
            nav_row.append(InlineKeyboardButton(text="➡️", callback_data="svc_next"))

        rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_service_card(service: dict) -> str:
    return (
        f"🔧 {service['title']}\n"
        f"📍 {service['city']}\n"
        f"📌 {service['address']}\n\n"
        f"{service.get('description') or ''}"
    )


async def send_service_card(message: Message, state: FSMContext, new_message: bool = False):
    data = await state.get_data()

    services = data.get("service_items", [])
    page = data.get("service_page", 1)
    total = data.get("service_total", 1)

    if not services:
        await message.answer("❌ No services found")
        return

    total_pages = max(1, math.ceil(len(services) / LIMIT))
    if total_pages != total:
        total = total_pages
        await state.update_data(service_total=total_pages)

    start = (page - 1) * LIMIT
    end = start + LIMIT
    current = services[start:end]

    if not current:
        await message.answer("❌ No services found")
        return

    service = current[0]

    await increment_views(service["id"])

    text = format_service_card(service)
    keyboard = build_service_card_kb(service, page, total)

    if new_message:
        if service.get("photo_id"):
            await message.answer_photo(
                photo=service["photo_id"],
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await message.answer(text, reply_markup=keyboard)
        return

    try:
        if message.photo and service.get("photo_id"):
            current_photo = message.photo[-1].file_id
            if current_photo != service["photo_id"]:
                await message.edit_media(
                    media=InputMediaPhoto(media=service["photo_id"], caption=text),
                    reply_markup=keyboard,
                )
            else:
                await message.edit_caption(caption=text, reply_markup=keyboard)
        elif service.get("photo_id"):
            await message.answer_photo(
                photo=service["photo_id"],
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await message.edit_text(text, reply_markup=keyboard)
    except Exception:
        if service.get("photo_id"):
            await message.answer_photo(
                photo=service["photo_id"],
                caption=text,
                reply_markup=keyboard,
            )
        else:
            await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "🔧 Find Service")
async def start_service_search_from_text(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ServiceStates.city)

    await message.answer(
        "🔧 Find Service\n\nChoose city from buttons or type your city:",
        reply_markup=service_city_kb(),
    )


@router.callback_query(F.data == "buyer:find_service")
async def start_service_search_from_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(ServiceStates.city)

    await callback.message.answer(
        "🔧 Find Service\n\nChoose city from buttons or type your city:",
        reply_markup=service_city_kb(),
    )


@router.callback_query(F.data.startswith("svc_city:"))
async def select_city_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    city = callback.data.split(":", 1)[1]

    await state.update_data(service_city=city)
    await state.set_state(ServiceStates.category)

    await callback.message.answer(
        "🧩 Select category",
        reply_markup=service_category_kb(),
    )


@router.message(ServiceStates.city)
async def select_city_text(message: Message, state: FSMContext):
    await state.update_data(service_city=message.text)
    await state.set_state(ServiceStates.category)

    await message.answer(
        "🧩 Select category",
        reply_markup=service_category_kb(),
    )


@router.callback_query(F.data.startswith("svc_category:"))
async def select_category_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    category = callback.data.split(":", 1)[1]

    data = await state.get_data()
    city = data.get("service_city")

    services = await get_services_by_filter(city, category)

    if not services:
        await callback.message.answer("😕 No services for this filter")
        await state.clear()
        return

    service_items = [dict(service) for service in services]
    total = max(1, math.ceil(len(service_items) / LIMIT))

    await state.update_data(
        service_city=city,
        service_category=category,
        service_items=service_items,
        service_page=1,
        service_total=total,
    )

    await callback.message.answer(f"🔎 Found services: {len(service_items)}")

    await send_service_card(callback.message, state, new_message=True)
    await state.set_state(None)


@router.callback_query(F.data == "svc_next")
async def next_service(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    page = data.get("service_page", 1)
    total = data.get("service_total", 1)

    if page >= total:
        await callback.answer("Це остання сторінка")
        return

    page += 1
    await state.update_data(service_page=page)

    await send_service_card(callback.message, state)


@router.callback_query(F.data == "svc_prev")
async def prev_service(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    page = data.get("service_page", 1)

    if page <= 1:
        await callback.answer("Це перша сторінка")
        return

    page -= 1
    await state.update_data(service_page=page)

    await send_service_card(callback.message, state)


@router.callback_query(F.data.startswith("svc_call:"))
async def service_call_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])
    await increment_calls(service_id)

    data = await state.get_data()
    service_items = data.get("service_items", [])

    service = next((item for item in service_items if item["id"] == service_id), None)

    if not service:
        await callback.message.answer("❌ Service not found")
        return

    await callback.message.answer(f"📞 {service.get('phone') or 'not specified'}")


@router.callback_query(F.data.startswith("svc_site:"))
async def service_site_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])

    data = await state.get_data()
    service_items = data.get("service_items", [])

    service = next((item for item in service_items if item["id"] == service_id), None)

    if not service:
        await callback.message.answer("❌ Service not found")
        return

    website = normalize_website(service.get("website"))

    if not website:
        await callback.message.answer("⚠️ Website not specified")
        return

    await increment_clicks(service_id)

    await callback.message.answer(
        "🌐 Website",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Open website", url=website)]]
        ),
    )
