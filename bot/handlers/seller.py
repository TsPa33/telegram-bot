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


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    brands = await get_brands()

    keyboard_buttons = [[KeyboardButton(text=b)] for b in brands]
    keyboard_buttons.append([KeyboardButton(text="➕ Додати новий бренд")])

    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True
    )

    await message.answer("Обери марку авто:", reply_markup=keyboard)
    await state.set_state(SellerStates.brand)


# ================= BRAND =================

@router.message(SellerStates.brand)
async def choose_brand(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "➕ Додати новий бренд":
        await message.answer("Введи назву нового бренду:")
        await state.set_state(SellerStates.new_brand)
        return

    brand = normalize_brand(text)

    if not validate_text(brand):
        await message.answer("❌ Некоректна марка")
        return

    models = await get_models_by_brand(brand)

    if not models:
        keyboard_buttons = [[KeyboardButton(text="➕ Додати нову модель")]]
    else:
        keyboard_buttons = [[KeyboardButton(text=m)] for m in models]
        keyboard_buttons.append([KeyboardButton(text="➕ Додати нову модель")])

    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True
    )

    await state.update_data(brand=brand)

    await message.answer("Обери модель:", reply_markup=keyboard)
    await state.set_state(SellerStates.model)


# ================= MODEL =================

@router.message(SellerStates.model)
async def choose_model(message: Message, state: FSMContext):
    text = message.text.strip()

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

    user_id = message.from_user.id
    username = message.from_user.username

    seller = await get_or_create_seller(user_id, username)

    model_id = await get_model_id(brand, model)

    if not model_id:
        await message.answer("❌ Помилка: модель не знайдена")
        return

    await add_seller_car(seller["id"], model_id, photo_id)

    await message.answer(f"✅ Авто додано: {brand} {model}")
    await state.clear()


# ❗ якщо не фото
@router.message(SellerStates.photo)
async def wrong_photo(message: Message):
    await message.answer("❌ Будь ласка, надішли саме фото")


# ================= NEW MODEL =================

@router.message(SellerStates.new_model)
async def add_new_model(message: Message, state: FSMContext):
    model = normalize_model(message.text)

    if not validate_text(model):
        await message.answer("❌ Некоректна назва моделі")
        return

    data = await state.get_data()
    brand = data.get("brand")
    user_id = message.from_user.id

    if await model_exists(brand, model):
        await message.answer("❗ Така модель вже існує")
        await state.clear()
        return

    await add_model_request(user_id, brand, model)

    await message.answer("⏳ Модель відправлена на модерацію")
    await state.clear()


# ================= NEW BRAND =================

@router.message(SellerStates.new_brand)
async def add_new_brand(message: Message, state: FSMContext):
    brand = normalize_brand(message.text)

    if not validate_text(brand):
        await message.answer("❌ Некоректна назва бренду")
        return

    user_id = message.from_user.id

    await add_brand_request(user_id, brand)

    await state.update_data(brand=brand)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="➕ Додати нову модель")]],
        resize_keyboard=True
    )

    await message.answer(
        "⏳ Бренд відправлено на модерацію\n"
        "Ти можеш одразу додати модель:",
        reply_markup=keyboard
    )

    await state.set_state(SellerStates.model)


# ================= MY CARS =================

@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message):
    cars = await get_seller_cars(message.from_user.id)

    if not cars:
        await message.answer("❌ У вас немає авто")
        return

    text = "🚗 Ваші авто:\n\n"

    for brand, model in cars:
        text += f"{brand} {model}\n"

    await message.answer(text)
