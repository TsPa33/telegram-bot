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

from bot.states.seller_states import SellerStates

from .verification import check_verified

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")
SKIP = KeyboardButton(text="Пропустити")


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):

    if not await check_verified(message, state):
        return

    await state.clear()

    brands = await get_cached_brands(get_brands)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


# ================= BRAND =================

@router.message(SellerStates.brand)
async def select_brand(message: Message, state: FSMContext):

    if not await check_verified(message, state):
        return

    if message.text == "⬅️ Назад":
        await state.clear()
        await message.answer("🏠 Меню", reply_markup=seller_menu_kb())
        return

    brands = await get_cached_brands(get_brands)

    if message.text not in brands:
        await message.answer("❌ Обери бренд з кнопок")
        return

    models = await get_cached_models(message.text, get_models_by_brand)

    if not models:
        await message.answer("❌ Моделей не знайдено")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
        resize_keyboard=True
    )

    await state.update_data(brand=message.text)
    await state.set_state(SellerStates.model)

    await message.answer("🚗 Обери модель:", reply_markup=keyboard)


# ================= MODEL =================

@router.message(SellerStates.model)
async def select_model(message: Message, state: FSMContext):

    if not await check_verified(message, state):
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

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[SKIP], [BACK]],
        resize_keyboard=True
    )

    await message.answer(
        "📸 Надішли фото авто або натисни 'Пропустити'",
        reply_markup=keyboard
    )


# ================= PHOTO =================

@router.message(SellerStates.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):

    if not await check_verified(message, state):
        return

    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)
    await state.set_state(SellerStates.description)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[SKIP], [BACK]],
        resize_keyboard=True
    )

    await message.answer("📝 Введи опис:", reply_markup=keyboard)


@router.message(SellerStates.photo)
async def skip_photo(message: Message, state: FSMContext):

    if not await check_verified(message, state):
        return

    if message.text == "Пропустити":
        await state.update_data(photo_id=None)
        await state.set_state(SellerStates.description)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[SKIP], [BACK]],
            resize_keyboard=True
        )

        await message.answer("📝 Введи опис:", reply_markup=keyboard)
        return

    if message.text == "⬅️ Назад":
        data = await state.get_data()
        brand = data.get("brand")

        models = await get_cached_models(brand, get_models_by_brand)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(SellerStates.model)
        await message.answer("🚗 Обери модель:", reply_markup=keyboard)
        return

    await message.answer("❌ Надішли фото або натисни 'Пропустити'")


# ================= DESCRIPTION =================

@router.message(SellerStates.description)
async def save_car(message: Message, state: FSMContext):

    if not await check_verified(message, state):
        return

    data = await state.get_data()

    # 🔙 НАЗАД
    if message.text == "⬅️ Назад":
        brand = data.get("brand")

        models = await get_cached_models(brand, get_models_by_brand)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(SellerStates.model)
        await message.answer("🚗 Обери модель:", reply_markup=keyboard)
        return

    description = None if message.text in ["Пропустити", "-"] else message.text

    # ================= EDIT =================
    if data.get("car_id"):
        await update_description(
            data["car_id"],
            description,
            message.from_user.id
        )

        await state.clear()

        await message.answer(
            "✅ Опис оновлено",
            reply_markup=seller_menu_kb()
        )
        return

    # ================= CREATE =================
    model_id = await get_model_id(data["brand"], data["model"])

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    await add_seller_car(
        seller_id=seller["id"],
        model_id=model_id,
        photo_id=data.get("photo_id"),
        description=description
    )

    await state.clear()

    await message.answer(
        "✅ Авто додано",
        reply_markup=seller_menu_kb()
    )
