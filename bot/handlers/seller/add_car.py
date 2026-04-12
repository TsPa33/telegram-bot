from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.keyboards.seller_menu import seller_menu_kb

from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    add_seller_car,
    update_description
)

from bot.database.repositories.model_repo import (
    get_brands,
    get_models_by_brand,
    get_model_id
)

from bot.utils.cache import get_cached_brands, get_cached_models
from bot.utils.formatters import format_car_card

from bot.states.seller_states import SellerStates


router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


# ================= CANCEL =================

@router.message(F.text == "/cancel")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Дію скасовано")


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    await state.clear()

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
    if await state.get_state() != SellerStates.brand:
        return

    if message.text == "⬅️ Назад":
        await state.clear()
        await message.answer("🏠 Меню", reply_markup=seller_menu_kb())
        return

    brands = await get_cached_brands(get_brands)

    if message.text not in brands:
        await message.answer("❌ Обери бренд з кнопок")
        return

    brand = message.text

    models = await get_cached_models(brand, get_models_by_brand)

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
    if await state.get_state() != SellerStates.model:
        return

    if message.text == "⬅️ Назад":
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(SellerStates.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    data = await state.get_data()
    brand = data.get("brand")

    models = await get_cached_models(brand, get_models_by_brand)

    if message.text not in models:
        await message.answer("❌ Обери модель з кнопок")
        return

    await state.update_data(model=message.text)
    await state.set_state(SellerStates.photo)

    await message.answer("📸 Надішли фото авто:")


# ================= BACK TO MODEL =================

@router.message(SellerStates.photo, F.text == "⬅️ Назад")
async def back_to_model(message: Message, state: FSMContext):
    if await state.get_state() != SellerStates.photo:
        return

    data = await state.get_data()
    brand = data.get("brand")

    models = await get_cached_models(brand, get_models_by_brand)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.model)
    await message.answer("🚗 Обери модель:", reply_markup=keyboard)


# ================= PHOTO =================

@router.message(SellerStates.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):
    if await state.get_state() != SellerStates.photo:
        return

    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Введи опис:")


@router.message(SellerStates.photo)
async def photo_error(message: Message, state: FSMContext):
    if await state.get_state() != SellerStates.photo:
        return

    await message.answer("❌ Надішли фото або натисни '⬅️ Назад'")


# ================= DESCRIPTION =================

@router.message(SellerStates.description)
async def save_car(message: Message, state: FSMContext):
    if await state.get_state() != SellerStates.description:
        return

    data = await state.get_data()

    description = (message.text or "").strip()

    if not description:
        await message.answer("❌ Введи опис")
        return

    # ================= EDIT MODE =================
    if data.get("car_id"):
        car_id = data["car_id"]

        # 🔴 SECURITY FIX
        await update_description(
            car_id,
            description,
            message.from_user.id
        )

        await message.answer("✅ Опис оновлено")

        await state.clear()
        return

    # ================= CREATE MODE =================
    brand = data.get("brand")
    model = data.get("model")
    photo_id = data.get("photo_id")

    model_id = await get_model_id(brand, model)

    if not model_id:
        await message.answer("❌ Модель не знайдена")
        await state.clear()
        return

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

    text = format_car_card(
        {
            "brand": brand,
            "model": model,
            "description": description
        },
        0,
        1
    )

    if photo_id:
        await message.answer_photo(
            photo=photo_id,
            caption=text,
            parse_mode="HTML"
        )
    else:
        await message.answer(
            text,
            parse_mode="HTML"
        )

    await state.clear()
