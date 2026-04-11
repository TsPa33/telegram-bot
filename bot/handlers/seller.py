from aiogram import Router, F, types
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
    get_seller_cars,
    delete_car,
    update_description
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
        await message.answer("🔙 Головне меню")
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

# ================= NEW MODEL =================

@router.message(SellerStates.new_model)
async def add_new_model(message: Message, state: FSMContext):
    model = normalize_model(message.text.strip())

    if not validate_text(model):
        await message.answer("❌ Некоректна модель")
        return

    data = await state.get_data()
    brand = data.get("brand")

    await add_model_request(
        message.from_user.id,
        brand,
        model
    )

    await message.answer("📩 Заявка на модель відправлена на модерацію")
    await state.clear()


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

    # 🔥 EDIT
    if car_id:
        await update_description(car_id, description)
        await message.answer("✅ Опис оновлено")
        await state.clear()
        return

    # 🔥 CREATE
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

    await message.answer("✅ Авто додано")
    await state.clear()


# ================= MY CARS (INLINE) =================

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


# ================= SELECT CAR =================

@router.callback_query(F.data.startswith("car_"))
async def select_car(callback: types.CallbackQuery):
    car_id = int(callback.data.split("_")[1])

    await callback.message.answer(
        "⚙️ Що зробити?",
        reply_markup=car_actions_kb(car_id)
    )

    await callback.answer()


# ================= DELETE =================

@router.callback_query(F.data.startswith("delete_"))
async def delete_car_handler(callback: types.CallbackQuery):
    car_id = int(callback.data.split("_")[1])

    await delete_car(car_id)

    await callback.message.answer("❌ Авто видалено")
    await callback.answer()


# ================= EDIT =================

@router.callback_query(F.data.startswith("edit_"))
async def edit_car_handler(callback: types.CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split("_")[1])

    await state.update_data(car_id=car_id)

    await callback.message.answer("📝 Введи новий опис:")
    await state.set_state(SellerStates.description)

    await callback.answer()


# ================= BACK =================

@router.message(F.text == "⬅️ Назад")
async def go_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔙 Головне меню")
