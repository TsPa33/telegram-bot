from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.database.db import (
    get_brands,
    get_models_by_brand,
    model_exists,
    add_model_request
)

from bot.states.seller import SellerStates
from bot.utils.validation import validate_text, normalize

router = Router()


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    brands = get_brands()

    if not brands:
        await message.answer("❌ Немає брендів")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands],
        resize_keyboard=True
    )

    await message.answer("Обери марку авто:", reply_markup=keyboard)
    await state.set_state(SellerStates.brand)


# ================= BRAND =================

@router.message(SellerStates.brand)
async def choose_brand(message: Message, state: FSMContext):
    brand = normalize(message.text)

    if not validate_text(brand):
        await message.answer("❌ Некоректна марка")
        return

    models = get_models_by_brand(brand)

    keyboard_buttons = [[KeyboardButton(text=m)] for m in models]

    # ➕ кнопка додавання нової моделі
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

    # ➕ перехід до нової моделі
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

    # ⚠️ тут просто лог (поки без seller_cars)
    await message.answer(f"✅ Обрано: {brand} {model}")

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

    # 🔍 перевірка дубля
    if model_exists(brand, model):
        await message.answer("❗ Така модель вже існує")
        await state.clear()
        return

    # 📩 створюємо заявку
    add_model_request(user_id, brand, model)

    await message.answer("⏳ Модель відправлена на модерацію")

    await state.clear()
