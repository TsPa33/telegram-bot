from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.keyboards.seller_menu import seller_menu_kb
from bot.keyboards.admin_inline import brand_request_kb, model_request_kb

from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    add_seller_car,
    has_available_slot
)

from bot.database.repositories.model_repo import (
    get_brands,
    get_models_by_brand,
    get_model_id
)

from bot.database.repositories.request_repo import (
    create_brand_request,
    create_model_request
)

from bot.utils.cache import get_cached_brands, get_cached_models

from bot.states.seller_states import SellerStates
from bot.config import ADMIN_IDS

from .verification import check_verified

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")
SKIP = KeyboardButton(text="Пропустити")

ADD_BRAND = KeyboardButton(text="➕ Додати бренд")
ADD_MODEL = KeyboardButton(text="➕ Додати модель")


@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    print("🔥 ADD_CAR_START")

    if not await check_verified(message, state):
        return

    if not await has_available_slot(message.from_user.id):
        await message.answer("❌ Немає доступних місць")
        return

    await state.clear()

    brands = await get_cached_brands(get_brands)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[ADD_BRAND], [BACK]],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


@router.message(SellerStates.brand)
async def select_brand(message: Message, state: FSMContext):
    print("🔥 SELECT BRAND:", message.text)

    if not await check_verified(message, state):
        return

    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)

    if message.text == "⬅️ Назад":
        await state.clear()
        await message.answer("🏠 Меню", reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False)))
        return

    if message.text == "➕ Додати бренд":
        await state.set_state(SellerStates.add_brand)
        await message.answer("✍️ Введи назву бренду:")
        return

    brands = await get_cached_brands(get_brands)

    if message.text not in brands:
        await message.answer("❌ Обери бренд з кнопок або додай новий")
        return

    models = await get_cached_models(message.text, get_models_by_brand)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[ADD_MODEL], [BACK]],
        resize_keyboard=True
    )

    await state.update_data(brand=message.text)
    await state.set_state(SellerStates.model)

    await message.answer("🚗 Обери модель:", reply_markup=keyboard)


@router.message(SellerStates.model)
async def select_model(message: Message, state: FSMContext):
    print("🔥 SELECT MODEL:", message.text)

    if not await check_verified(message, state):
        return

    if message.text == "⬅️ Назад":
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[ADD_BRAND], [BACK]],
            resize_keyboard=True
        )

        await state.set_state(SellerStates.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    data = await state.get_data()
    brand = data.get("brand")

    models = await get_cached_models(brand, get_models_by_brand)

    if message.text not in models:
        await message.answer("❌ Обери модель з кнопок або додай нову")
        return

    await state.update_data(model=message.text)
    await state.set_state(SellerStates.photo)

    await message.answer("📸 Надішли фото або 'Пропустити'")


@router.message(SellerStates.photo, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    print("🔥 PHOTO RECEIVED")

    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Введи опис або 'Пропустити'")


@router.message(SellerStates.photo, F.text == "Пропустити")
async def skip_photo(message: Message, state: FSMContext):
    print("🔥 PHOTO SKIPPED")

    await state.update_data(photo_id=None)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Введи опис або 'Пропустити'")


@router.message(SellerStates.description, F.text == "Пропустити")
async def skip_description(message: Message, state: FSMContext):
    print("🔥 DESCRIPTION SKIPPED")

    data = await state.get_data()

    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)
    model_id = await get_model_id(data["brand"], data["model"])

    await add_seller_car(
        seller_id=seller["id"],
        model_id=model_id,
        photo_id=data.get("photo_id"),
        description=None
    )

    await message.answer("✅ Авто додано", reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False)))
    await state.clear()


@router.message(SellerStates.description)
async def handle_description(message: Message, state: FSMContext):
    print("🔥 DESCRIPTION:", message.text)

    data = await state.get_data()

    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)
    model_id = await get_model_id(data["brand"], data["model"])

    await add_seller_car(
        seller_id=seller["id"],
        model_id=model_id,
        photo_id=data.get("photo_id"),
        description=message.text
    )

    await message.answer("✅ Авто додано", reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False)))
    await state.clear()
