from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.utils.cache import get_cached_brands, get_cached_models

from bot.database.repositories.model_repo import (
    get_brands,
    get_models_by_brand,
    model_exists,
    get_model_id
)

from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    add_seller_car,
    get_seller_cars
)

from bot.database.repositories.request_repo import (
    add_model_request,
    add_brand_request
)

from bot.states.seller import SellerStates
from bot.utils.validation import validate_text, normalize_brand, normalize_model

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    brands = await get_cached_brands(get_brands)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] +
                 [[KeyboardButton(text="➕ Додати новий бренд")]] +
                 [[BACK]],
        resize_keyboard=True
    )

    await message.answer("Обери марку авто:", reply_markup=keyboard)
    await state.set_state(SellerStates.brand)


# ================= BRAND =================

@router.message(SellerStates.brand)
async def choose_brand(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "⬅️ Назад":
        await state.clear()
        await message.answer("🔙 Головне меню")
        return

    if text == "➕ Додати новий бренд":
        await message.answer("Введи назву нового бренду:")
        await state.set_state(SellerStates.new_brand)
        return

    brand = normalize_brand(text)

    if not validate_text(brand):
        await message.answer("❌ Некоректна марка")
        return

    models = await get_cached_models(brand, get_models_by_brand)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] +
                 [[KeyboardButton(text="➕ Додати нову модель")]] +
                 [[BACK]],
        resize_keyboard=True
    )

    await state.update_data(brand=brand)
    await message.answer("Обери модель:", reply_markup=keyboard)
    await state.set_state(SellerStates.model)


# ================= MODEL =================

@router.message(SellerStates.model)
async def choose_model(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "⬅️ Назад":
        await add_car_start(message, state)
        return

    if text == "➕ Додати нову модель":
        await message.answer("Введи назву нової моделі:")
        await state.set_state(SellerStates.new_model)
        return

    model = normalize_model(text)

    if not validate_text(model):
        await message.answer("❌ Некоректна модель")
        return

    data = await state.get_data()
    brand = data.get("brand")

    if not await model_exists(brand, model):
        await message.answer("❌ Такої моделі немає")
        return

    await state.update_data(model=model)

    await message.answer("📸 Надішли фото авто")
    await state.set_state(SellerStates.photo)


# ================= PHOTO =================

@router.message(SellerStates.photo, F.photo)
async def add_car_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id

    data = await state.get_data()
    brand = data.get("brand")
    model = data.get("model")

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    model_id = await get_model_id(brand, model)

    if not model_id:
        await message.answer("❌ Помилка")
        return

    await add_seller_car(seller["id"], model_id, photo_id)

    await message.answer(f"✅ Авто додано: {brand} {model}")
    await state.clear()


@router.message(SellerStates.photo)
async def wrong_photo(message: Message):
    if message.text == "⬅️ Назад":
        data = await message.bot.get("state_data", {})
    await message.answer("❌ Надішли фото")


# ================= BACK HANDLER =================

@router.message(F.text == "⬅️ Назад")
async def go_back_seller(message: Message, state: FSMContext):
    current = await state.get_state()

    if current == SellerStates.model:
        await add_car_start(message, state)

    elif current == SellerStates.photo:
        data = await state.get_data()
        brand = data.get("brand")

        models = await get_cached_models(brand, get_models_by_brand)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
            resize_keyboard=True
        )

        await message.answer("Обери модель:", reply_markup=keyboard)
        await state.set_state(SellerStates.model)

    else:
        await state.clear()
        await message.answer("🔙 Головне меню")
