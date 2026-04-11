from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.keyboards.seller_menu import seller_menu_kb
from bot.keyboards.seller_inline import cars_list_kb, car_actions_kb

from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    delete_car,
    update_description,
    add_seller_car
)

from bot.database.repositories.car_repo import get_seller_cars
from bot.database.repositories.model_repo import (
    get_brands,
    get_models_by_brand,
    get_model_id
)

from bot.utils.cache import get_cached_brands, get_cached_models

from bot.states.seller import SellerStates

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    brands = await get_cached_brands(get_brands)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.brand)

    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


# ================= SELECT BRAND =================

@router.message(SellerStates.brand)
async def select_brand(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.clear()
        await message.answer("🏠 Меню", reply_markup=seller_menu_kb())
        return

    brand = message.text

    models = await get_cached_models(brand)

    if not models:
        await message.answer("❌ Моделей не знайдено")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
        resize_keyboard=True
    )

    await state.update_data(brand=brand)
    await state.set_state(SellerStates.model)

    await message.answer("🚗 Обери модель:", reply_markup=keyboard)


# ================= SELECT MODEL =================

@router.message(SellerStates.model)
async def select_model(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        data = await state.get_data()
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(SellerStates.brand)

        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    model = message.text

    await state.update_data(model=model)
    await state.set_state(SellerStates.photo)

    await message.answer("📸 Надішли фото авто:")


# ================= PHOTO =================

@router.message(SellerStates.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Введи опис:")


@router.message(SellerStates.photo)
async def photo_error(message: Message):
    await message.answer("❌ Надішли саме фото")


# ================= DESCRIPTION =================

@router.message(SellerStates.description)
async def save_car(message: Message, state: FSMContext):
    data = await state.get_data()

    brand = data.get("brand")
    model = data.get("model")
    photo_id = data.get("photo_id")
    description = message.text

    model_id = await get_model_id(brand, model)

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    await add_seller_car(
        seller_id=seller["id"],
        model_id=model_id,
        photo_id=photo_id,
        description=description
    )

    await message.answer("✅ Авто додано")

    await message.answer_photo(
        photo=photo_id,
        caption=f"🚗 {brand} {model}\n\n{description}"
    )

    await state.clear()

    await message.answer("🏠 Меню", reply_markup=seller_menu_kb())


# ================= PROFILE =================

@router.message(F.text == "👤 Профіль")
async def seller_profile(message: Message):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    cars = await get_seller_cars(message.from_user.id)

    username = seller.get("username")
    username_text = f"@{username}" if username else "немає"

    text = (
        f"👤 <b>Твій профіль</b>\n\n"
        f"ID: {seller.get('id')}\n"
        f"Username: {username_text}\n"
        f"🚗 Авто: {len(cars)}"
    )

    await message.answer(text, parse_mode="HTML")


# ================= MY CARS =================

@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message):
    cars = await get_seller_cars(message.from_user.id)

    if not cars:
        await message.answer("❌ У вас немає авто")
        return

    await message.answer("🚗 Обери авто:")

    await message.answer(
        "👇 Список авто:",
        reply_markup=cars_list_kb(cars)
    )


# ================= OPEN CAR =================

@router.callback_query(F.data.startswith("car_"))
async def open_car(callback: types.CallbackQuery):
    car_id = int(callback.data.split("_")[1])

    await callback.answer()

    await callback.message.answer(
        f"🚗 Авто ID: {car_id}",
        reply_markup=car_actions_kb(car_id)
    )

    await callback.message.answer("🏠 Меню", reply_markup=seller_menu_kb())


# ================= DELETE =================

@router.callback_query(F.data.startswith("delete_"))
async def delete_car_handler(callback: types.CallbackQuery):
    car_id = int(callback.data.split("_")[1])

    await delete_car(car_id)

    await callback.answer("Видалено")

    await callback.message.answer("❌ Авто видалено")
    await callback.message.answer("🏠 Меню", reply_markup=seller_menu_kb())


# ================= EDIT =================

@router.callback_query(F.data.startswith("edit_"))
async def edit_car_handler(callback: types.CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split("_")[1])

    await state.update_data(car_id=car_id)

    await callback.answer()
    await callback.message.answer("📝 Введи новий опис:")

    await state.set_state(SellerStates.description)


# ================= SAVE DESCRIPTION =================

@router.message(SellerStates.description)
async def save_description(message: Message, state: FSMContext):
    data = await state.get_data()
    car_id = data.get("car_id")

    if car_id:
        await update_description(car_id, message.text)
        await message.answer("✅ Опис оновлено")

        await state.clear()
        await message.answer("🏠 Меню", reply_markup=seller_menu_kb())
