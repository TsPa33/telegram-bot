from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.database.db import (
    get_brands,
    get_models_by_brand,
    model_exists,
    add_model_request,
    get_or_create_seller,
    add_seller_car,
    get_seller_cars
)

from bot.states.seller import SellerStates
from bot.utils.validation import validate_text, normalize

router = Router()


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    brands = get_brands()

    # створюємо список кнопок
    keyboard_buttons = [[KeyboardButton(text=b)] for b in brands]

    # додаємо кнопку нового бренду
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

    # ================= НОВИЙ БРЕНД =================
    if text == "➕ Додати новий бренд":
        await message.answer("Введи назву нового бренду:")
        await state.set_state(SellerStates.new_brand)
        return

    # ================= ЗВИЧАЙНИЙ БРЕНД =================
    brand = normalize(text)

    if not validate_text(brand):
        await message.answer("❌ Некоректна марка")
        return

    models = get_models_by_brand(brand)

    keyboard_buttons = [[KeyboardButton(text=m)] for m in models]

    # кнопка нової моделі
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

    # ➕ нова модель
    if text == "➕ Додати нову модель":
        await message.answer("Введи назву нової моделі:")
        await state.set_state(SellerStates.new_model)
        return

    model = normalize(text)

    if not validate_text(model):
        await message.answer("❌ Некоректна модель")
        return

    data = await state.get_data()
    brand = data.get("brand")

    # 🔥 створюємо/отримуємо seller
    user_id = message.from_user.id
    username = message.from_user.username

    seller_id = get_or_create_seller(user_id, username)

    # 🔥 додаємо авто
    add_seller_car(seller_id, brand, model)

    await message.answer(f"✅ Авто додано: {brand} {model}")

    await state.clear()


# ================= NEW MODEL =================

@router.message(SellerStates.new_model)
async def add_new_model(message: Message, state: FSMContext):
    model = normalize(message.text)

    if not validate_text(model):
        await message.answer("❌ Некоректна назва моделі")
        return

    data = await state.get_data()
    brand = data.get("brand")
    user_id = message.from_user.id

    # 🔍 дубль
    if model_exists(brand, model):
        await message.answer("❗ Така модель вже існує")
        await state.clear()
        return

    # 📩 заявка
    add_model_request(user_id, brand, model)

    await message.answer("⏳ Модель відправлена на модерацію")

    await state.clear()


# ================= MY CARS =================

@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message):
    cars = get_seller_cars(message.from_user.id)

    if not cars:
        await message.answer("❌ У вас немає авто")
        return

    text = "🚗 Ваші авто:\n\n"

    for brand, model in cars:
        text += f"{brand} {model}\n"

    await message.answer(text)
