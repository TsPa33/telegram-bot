from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.keyboards.seller_menu import seller_menu_kb
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
    get_seller_cars,
    delete_car,
    update_description
)

from bot.database.repositories.request_repo import (
    add_model_request,
    add_brand_request
)

from bot.keyboards.seller_inline import cars_list_kb, car_actions_kb

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

    await message.answer("🚗 Обери марку авто:", reply_markup=keyboard)
    await state.set_state(SellerStates.brand)


# ================= BRAND =================

@router.message(SellerStates.brand)
async def choose_brand(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "⬅️ Назад":
        await state.clear()
        await message.answer("🏠 Головне меню", reply_markup=seller_menu_kb())
        return

    if text == "➕ Додати новий бренд":
        await message.answer("Введи назву бренду:")
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
    await message.answer("🚘 Обери модель:", reply_markup=keyboard)
    await state.set_state(SellerStates.model)


# ================= MODEL =================

@router.message(SellerStates.model)
async def choose_model(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "⬅️ Назад":
        await add_car_start(message, state)
        return

    if text == "➕ Додати нову модель":
        await message.answer("Введи модель:")
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
async def add_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)

    await message.answer("📝 Додай опис авто:")
    await state.set_state(SellerStates.description)


# ================= DESCRIPTION =================

@router.message(SellerStates.description)
async def add_description(message: Message, state: FSMContext):
    description = message.text.strip()

    data = await state.get_data()
    car_id = data.get("car_id")

    if car_id:
        await update_description(car_id, description)
        await message.answer("✅ Опис оновлено")
        await state.clear()
        await message.answer("🏠 Меню", reply_markup=seller_menu_kb())
        return

    brand = data.get("brand")
    model = data.get("model")
    photo_id = data.get("photo_id")

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    model_id = await get_model_id(brand, model)

    await add_seller_car(
        seller["id"],
        model_id,
        photo_id,
        description
    )

    await message.answer_photo(
        photo_id,
        caption=f"🚗 {brand} {model}\n\n📝 {description}"
    )

    await state.clear()
    await message.answer("🏠 Меню", reply_markup=seller_menu_kb())


# ================= MY CARS =================

@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message):
    cars = await get_seller_cars(message.from_user.id)

    if not cars:
        await message.answer("❌ У вас немає авто")
        return

    await message.answer(
        "🚗 Обери авто:",
        reply_markup=cars_list_kb(cars)
    )


# ================= PROFILE =================

@router.message(F.text == "👤 Профіль")
async def seller_profile(message: Message):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    cars = await get_seller_cars(message.from_user.id)

    text = (
        f"👤 <b>Твій профіль</b>\n\n"
        f"ID: {seller['id']}\n"
        f"Username: @{seller['username'] if seller['username'] else 'немає'}\n"
        f"🚗 Авто: {len(cars)}"
    )

    await message.answer(text, parse_mode="HTML")
