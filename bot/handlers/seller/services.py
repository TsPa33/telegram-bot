from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states.service_states import ServiceStates
from bot.database.repositories.service_repo import (
    create_service,
    get_services_by_seller,
    delete_service
)

router = Router()


# ================= ADD SERVICE =================

@router.message(F.text == "➕ Додати послугу")
async def add_service_start(message: Message, state: FSMContext):
    await state.set_state(ServiceStates.category)

    await message.answer(
        "Оберіть категорію:",
        reply_markup=None  # можна додати кнопки пізніше
    )


@router.message(ServiceStates.category)
async def set_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(ServiceStates.photo)

    await message.answer("📸 Надішліть фото послуги")


@router.message(ServiceStates.photo, F.photo)
async def set_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)
    await state.set_state(ServiceStates.title)

    await message.answer("Введіть назву послуги")


@router.message(ServiceStates.title)
async def set_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(ServiceStates.city)

    await message.answer("Введіть місто")


@router.message(ServiceStates.city)
async def set_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(ServiceStates.address)

    await message.answer("Введіть адресу")


@router.message(ServiceStates.address)
async def set_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(ServiceStates.description)

    await message.answer("Введіть опис")


@router.message(ServiceStates.description)
async def set_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(ServiceStates.website)

    await message.answer("Введіть сайт або напишіть '-' щоб пропустити")


@router.message(ServiceStates.website)
async def set_website(message: Message, state: FSMContext):
    data = await state.get_data()

    website = None if message.text == "-" else message.text

    await create_service(
        seller_id=message.from_user.id,
        category=data["category"],
        title=data["title"],
        city=data["city"],
        address=data["address"],
        description=data["description"],
        website=website,
        photo_id=data["photo_id"],
    )

    await state.clear()

    await message.answer("✅ Послугу додано!")


# ================= MY SERVICES =================

@router.message(F.text == "📋 Мої послуги")
async def my_services(message: Message):
    services = await get_services_by_seller(message.from_user.id)

    if not services:
        await message.answer("У вас ще немає послуг")
        return

    for s in services:
        text = f"🔧 {s['title']}\n📍 {s['city']}\n📌 {s['address']}"

        await message.answer(
            text,
            reply_markup=None  # додамо кнопки пізніше
        )


# ================= DELETE =================

@router.callback_query(F.data.startswith("service_delete:"))
async def delete_service_handler(callback: CallbackQuery):
    service_id = int(callback.data.split(":")[1])

    await delete_service(service_id)

    await callback.message.answer("🗑 Послугу видалено")
    await callback.answer()
