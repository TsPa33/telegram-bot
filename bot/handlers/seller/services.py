from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot.database.repositories.service_repo import (
    create_service,
    delete_service,
    get_services_by_seller,
    update_service,
)
from bot.database.repositories.seller_repo import get_or_create_seller, get_seller_by_telegram_id
from bot.keyboards.seller_menu import seller_menu_kb
from bot.states.service_states import ServiceStates
from .verification import check_verified

router = Router()

SERVICE_CATEGORIES = [
    "СТО",
    "Детейлінг",
    "Евакуатор",
    "Шиномонтаж",
    "Автоелектрик",
]


ADD_SERVICE_BACK = KeyboardButton(text="⬅️ Назад у мій профіль")
SKIP_WEBSITE = KeyboardButton(text="⚠️ Пропустити")


EDIT_FIELDS = {
    "title": "Назва",
    "city": "Місто",
    "address": "Адреса",
    "description": "Опис",
    "website": "Сайт",
}


def service_categories_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [ADD_SERVICE_BACK],
            *[[KeyboardButton(text=category)] for category in SERVICE_CATEGORIES],
        ],
        resize_keyboard=True,
    )


def skip_website_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[SKIP_WEBSITE]],
        resize_keyboard=True,
    )


def seller_services_list_kb(services: list) -> InlineKeyboardMarkup:
    rows = []

    for service in services:
        rows.append(
            [
                InlineKeyboardButton(
                    text=service["title"],
                    callback_data=f"service:{service['id']}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def seller_service_actions_kb(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Edit", callback_data=f"service_edit:{service_id}"),
                InlineKeyboardButton(text="🗑 Delete", callback_data=f"service_delete:{service_id}"),
            ]
        ]
    )


def seller_service_edit_fields_kb(service_id: int) -> InlineKeyboardMarkup:
    rows = []
    for field, title in EDIT_FIELDS.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"service_edit_field:{service_id}:{field}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _get_service_for_seller(telegram_id: int, service_id: int):
    seller = await get_seller_by_telegram_id(telegram_id)
    if not seller:
        return None, None

    services = await get_services_by_seller(seller["id"])

    for service in services:
        if service["id"] == service_id:
            return seller, service

    return seller, None


@router.message(F.text == "➕ Add Service")
async def add_service_start(message: Message, state: FSMContext):
    if not await check_verified(message, state):
        return

    await state.clear()
    await state.set_state(ServiceStates.category)
    await message.answer("🔧 Select category", reply_markup=service_categories_kb())


@router.message(ServiceStates.category)
async def add_service_category(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад у мій профіль":
        seller = await get_or_create_seller(message.from_user.id, message.from_user.username)
        await state.clear()
        await message.answer(
            "🏠 Меню",
            reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False)),
        )
        return

    if message.text not in SERVICE_CATEGORIES:
        await message.answer("❌ Оберіть категорію з кнопок")
        return

    await state.update_data(category=message.text)
    await state.set_state(ServiceStates.photo)
    await message.answer("📷 Upload service photo")


@router.message(ServiceStates.photo, F.photo)
async def add_service_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(ServiceStates.title)
    await message.answer("📝 Enter service title")


@router.message(ServiceStates.photo)
async def add_service_photo_invalid(message: Message):
    await message.answer("❌ Надішліть фото сервісу")


@router.message(ServiceStates.title)
async def add_service_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(ServiceStates.city)
    await message.answer("📍 Enter city")


@router.message(ServiceStates.city)
async def add_service_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(ServiceStates.address)
    await message.answer("📌 Enter address")


@router.message(ServiceStates.address)
async def add_service_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(ServiceStates.description)
    await message.answer("🧾 Enter description")


@router.message(ServiceStates.description)
async def add_service_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(ServiceStates.website)
    await message.answer("🌐 Enter website or skip", reply_markup=skip_website_kb())


@router.message(ServiceStates.website, F.text == "⚠️ Пропустити")
async def add_service_website_skip(message: Message, state: FSMContext):
    data = await state.get_data()

    if data.get("edit_mode"):
        field = data.get("edit_field")
        service_id = data.get("edit_service_id")

        await update_service(service_id, field, None)

        await state.update_data(edit_mode=False, edit_field=None, edit_service_id=None)
        await state.set_state(None)
        await message.answer("✅ Updated")
        return

    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)

    service_id = await create_service(
        seller_id=seller["id"],
        category=data["category"],
        title=data["title"],
        city=data["city"],
        address=data["address"],
        description=data.get("description"),
        website=None,
        photo_id=data.get("photo_id"),
    )

    await state.clear()
    await message.answer(
        f"✅ Service added (ID: {service_id})",
        reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False)),
    )


@router.message(ServiceStates.website)
async def add_service_website(message: Message, state: FSMContext):
    data = await state.get_data()

    if data.get("edit_mode"):
        field = data.get("edit_field")
        service_id = data.get("edit_service_id")

        await update_service(service_id, field, message.text)

        await state.update_data(edit_mode=False, edit_field=None, edit_service_id=None)
        await state.set_state(None)
        await message.answer("✅ Updated")
        return

    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)

    service_id = await create_service(
        seller_id=seller["id"],
        category=data["category"],
        title=data["title"],
        city=data["city"],
        address=data["address"],
        description=data.get("description"),
        website=message.text,
        photo_id=data.get("photo_id"),
    )

    await state.clear()
    await message.answer(
        f"✅ Service added (ID: {service_id})",
        reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False)),
    )


@router.message(F.text == "📋 My Services")
async def my_services(message: Message):
    seller = await get_seller_by_telegram_id(message.from_user.id)

    if not seller:
        await message.answer("❌ Seller not found")
        return

    services = await get_services_by_seller(seller["id"])

    if not services:
        await message.answer("📭 No services yet")
        return

    await message.answer("📋 My Services", reply_markup=seller_services_list_kb(services))


@router.callback_query(F.data.startswith("service:"))
async def open_service(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])

    _, service = await _get_service_for_seller(callback.from_user.id, service_id)

    if not service:
        await callback.message.answer("❌ Service not found")
        return

    text = (
        f"🔧 {service['title']}\n"
        f"📍 {service['city']}\n"
        f"📌 {service['address']}\n\n"
        f"{service.get('description') or ''}"
    )

    if service.get("photo_id"):
        await callback.message.answer_photo(
            photo=service["photo_id"],
            caption=text,
            reply_markup=seller_service_actions_kb(service_id),
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=seller_service_actions_kb(service_id),
        )


@router.callback_query(F.data.startswith("service_delete:"))
async def delete_service_handler(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])
    _, service = await _get_service_for_seller(callback.from_user.id, service_id)

    if not service:
        await callback.message.answer("❌ Service not found")
        return

    await delete_service(service_id)
    await callback.message.answer("✅ Deleted")


@router.callback_query(F.data.startswith("service_edit:"))
async def edit_service_handler(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])
    _, service = await _get_service_for_seller(callback.from_user.id, service_id)

    if not service:
        await callback.message.answer("❌ Service not found")
        return

    await callback.message.answer(
        "✏️ Choose field to edit",
        reply_markup=seller_service_edit_fields_kb(service_id),
    )


@router.callback_query(F.data.startswith("service_edit_field:"))
async def edit_service_field_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    _, service_id_text, field = callback.data.split(":")
    service_id = int(service_id_text)

    _, service = await _get_service_for_seller(callback.from_user.id, service_id)

    if not service:
        await callback.message.answer("❌ Service not found")
        return

    await state.update_data(edit_mode=True, edit_service_id=service_id, edit_field=field)
    await state.set_state(ServiceStates.website)

    await callback.message.answer(
        f"✍️ Enter new value for {EDIT_FIELDS[field]}\n"
        "Для очищення сайту натисни ⚠️ Пропустити",
        reply_markup=skip_website_kb(),
    )
