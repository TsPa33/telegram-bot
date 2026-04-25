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

ADD_SERVICE_BACK = KeyboardButton(text="⬅️ Назад у профіль")
SKIP_WEBSITE = KeyboardButton(text="⚠️ Пропустити")

EDIT_FIELDS = {
    "title": "Назва",
    "city": "Місто",
    "address": "Адреса",
    "description": "Опис",
    "website": "Сайт",
}


# ================= KEYBOARDS =================

def service_categories_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [ADD_SERVICE_BACK],
            *[[KeyboardButton(text=cat)] for cat in SERVICE_CATEGORIES],
        ],
        resize_keyboard=True,
    )


def skip_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[SKIP_WEBSITE]],
        resize_keyboard=True,
    )


def services_list_kb(services):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=s["title"], callback_data=f"service:{s['id']}")]
            for s in services
        ]
    )


def actions_kb(service_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"service_edit:{service_id}"),
                InlineKeyboardButton(text="🗑 Видалити", callback_data=f"service_delete:{service_id}"),
            ]
        ]
    )


def edit_fields_kb(service_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=name,
                    callback_data=f"service_edit_field:{service_id}:{field}",
                )
            ]
            for field, name in EDIT_FIELDS.items()
        ]
    )


# ================= ADD SERVICE =================

@router.message(F.text == "➕ Додати послугу")
async def start_add(message: Message, state: FSMContext):
    if not await check_verified(message, state):
        return

    await state.clear()
    await state.set_state(ServiceStates.category)

    await message.answer("Оберіть категорію:", reply_markup=service_categories_kb())


@router.message(ServiceStates.category)
async def set_category(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад у профіль":
        seller = await get_or_create_seller(message.from_user.id, message.from_user.username)
        await state.clear()
        await message.answer("Меню", reply_markup=seller_menu_kb(seller.get("is_verified")))
        return

    if message.text not in SERVICE_CATEGORIES:
        await message.answer("Оберіть категорію з кнопок")
        return

    await state.update_data(category=message.text)
    await state.set_state(ServiceStates.photo)
    await message.answer("Надішліть фото")


@router.message(ServiceStates.photo, F.photo)
async def set_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(ServiceStates.title)
    await message.answer("Назва")


@router.message(ServiceStates.title)
async def set_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(ServiceStates.city)
    await message.answer("Місто")


@router.message(ServiceStates.city)
async def set_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(ServiceStates.address)
    await message.answer("Адреса")


@router.message(ServiceStates.address)
async def set_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(ServiceStates.description)
    await message.answer("Опис")


@router.message(ServiceStates.description)
async def set_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(ServiceStates.website)
    await message.answer("Сайт або пропустити", reply_markup=skip_kb())


@router.message(ServiceStates.website)
async def set_website(message: Message, state: FSMContext):
    data = await state.get_data()

    website = None if message.text == "⚠️ Пропустити" else message.text

    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)

    await create_service(
        seller_id=seller["id"],
        category=data["category"],
        title=data["title"],
        city=data["city"],
        address=data["address"],
        description=data.get("description"),
        website=website,
        photo_id=data.get("photo_id"),
    )

    await state.clear()

    await message.answer(
        "✅ Послугу додано",
        reply_markup=seller_menu_kb(seller.get("is_verified")),
    )


# ================= MY SERVICES =================

@router.message(F.text == "📋 Мої послуги")
async def my_services(message: Message):
    seller = await get_seller_by_telegram_id(message.from_user.id)

    if not seller:
        await message.answer("❌ Помилка продавця")
        return

    services = await get_services_by_seller(seller["id"])

    if not services:
        await message.answer("У вас немає послуг")
        return

    await message.answer("Ваші послуги:", reply_markup=services_list_kb(services))


@router.callback_query(F.data.startswith("service:"))
async def open_service(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])
    seller = await get_seller_by_telegram_id(callback.from_user.id)
    services = await get_services_by_seller(seller["id"])

    service = next((s for s in services if s["id"] == service_id), None)

    if not service:
        await callback.message.answer("❌ Не знайдено")
        return

    text = (
        f"🔧 {service['title']}\n"
        f"📍 {service['city']}\n"
        f"📌 {service['address']}"
    )

    await callback.message.answer(text, reply_markup=actions_kb(service_id))


# ================= DELETE =================

@router.callback_query(F.data.startswith("service_delete:"))
async def delete_handler(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])
    await delete_service(service_id)

    await callback.message.answer("🗑 Видалено")