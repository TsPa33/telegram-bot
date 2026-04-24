from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.keyboards.seller_menu import seller_menu_kb

from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    add_seller_car
)

from bot.database.repositories.model_repo import (
    get_brands,
    get_models_by_brand,
    get_model_id
)

from bot.utils.cache import get_cached_brands, get_cached_models
from bot.states.seller_states import SellerStates

router = Router()


# ================= HELPERS =================

def brand_keyboard(brands):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Назад у мій профіль")],
            [KeyboardButton(text="➕ Додати новий бренд")]
        ] + [[KeyboardButton(text=b)] for b in brands],
        resize_keyboard=True
    )


def model_keyboard(models):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Назад")],
            [KeyboardButton(text="➕ Додати нову модель")]
        ] + [[KeyboardButton(text=m)] for m in models],
        resize_keyboard=True
    )


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    brands = await get_cached_brands(get_brands)

    await state.set_state(SellerStates.brand)

    await message.answer(
        "🚗 Обери бренд:",
        reply_markup=brand_keyboard(brands)
    )


# ================= SELECT BRAND =================

@router.message(SellerStates.brand)
async def select_brand(message: Message, state: FSMContext):

    if message.text == "⬅️ Назад у мій профіль":
        await state.clear()
        seller = await get_or_create_seller(message.from_user.id, message.from_user.username)

        await message.answer(
            "🏠 Меню",
            reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False))
        )
        return

    if message.text == "➕ Додати новий бренд":
        await message.answer("✏️ Введи назву нового бренду")
        return

    models = await get_cached_models(message.text, get_models_by_brand)

    if not models:
        await message.answer("❌ Моделей не знайдено")
        return

    await state.update_data(brand=message.text)
    await state.set_state(SellerStates.model)

    await message.answer(
        "🚗 Обери модель:",
        reply_markup=model_keyboard(models)
    )


# ================= SELECT MODEL =================

@router.message(SellerStates.model)
async def select_model(message: Message, state: FSMContext):

    if message.text == "⬅️ Назад":
        brands = await get_cached_brands(get_brands)

        await state.set_state(SellerStates.brand)
        await message.answer(
            "🚗 Обери бренд:",
            reply_markup=brand_keyboard(brands)
        )
        return

    if message.text == "➕ Додати нову модель":
        await message.answer("✏️ Введи назву нової моделі")
        return

    await state.update_data(model=message.text)
    await state.set_state(SellerStates.photo)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Назад до брендів")],
            [KeyboardButton(text="⚠️ Пропустити")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Натисни 📎 та вибери фото авто і надішли його нам\n\n"
        "ℹ️ Можна пропустити цей крок але авто з фото викликає довіру у покупців",
        reply_markup=keyboard
    )


# ================= PHOTO =================

@router.message(SellerStates.photo, F.text == "⬅️ Назад до брендів")
async def back_to_brands(message: Message, state: FSMContext):
    brands = await get_cached_brands(get_brands)

    await state.set_state(SellerStates.brand)
    await message.answer(
        "🚗 Обери бренд:",
        reply_markup=brand_keyboard(brands)
    )


@router.message(SellerStates.photo, F.text == "⚠️ Пропустити")
async def skip_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=None)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Напиши кілька слів для опису")


@router.message(SellerStates.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Напиши кілька слів для опису")


# ================= DESCRIPTION =================

@router.message(SellerStates.description)
async def save_car(message: Message, state: FSMContext):
    data = await state.get_data()

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    model_id = await get_model_id(data["brand"], data["model"])

    await add_seller_car(
        seller_id=seller["id"],
        model_id=model_id,
        photo_id=data.get("photo_id"),
        description=message.text or "Без опису"
    )

    await message.answer(
        "✅ Авто додано",
        reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False))
    )

    await state.clear()
