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

from bot.database.repositories.request_repo import (
    create_brand_request,
    create_model_request
)

from bot.utils.cache import get_cached_brands, get_cached_models

from bot.states.seller_states import SellerStates

from .verification import check_verified

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")
SKIP = KeyboardButton(text="Пропустити")

ADD_BRAND = KeyboardButton(text="➕ Додати бренд")
ADD_MODEL = KeyboardButton(text="➕ Додати модель")


# ================= ADD CAR =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    if not await check_verified(message, state):
        return

    await state.clear()

    brands = await get_cached_brands(get_brands)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[ADD_BRAND], [BACK]],
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

    # ➕ ДОДАТИ БРЕНД
    if message.text == "➕ Додати бренд":
        await state.set_state(SellerStates.add_brand)
        await message.answer("✍️ Введи назву бренду:")
        return

    brands = await get_cached_brands(get_brands)

    if message.text not in brands:
        await message.answer("❌ Обери бренд з кнопок або додай новий")
        return

    models = await get_cached_models(message.text, get_models_by_brand)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[ADD_MODEL], [BACK]],
        resize_keyboard=True
    )

    await state.update_data(brand=message.text)
    await state.set_state(SellerStates.model)

    await message.answer("🚗 Обери модель:", reply_markup=keyboard)


# ================= ADD BRAND =================

@router.message(SellerStates.add_brand)
async def add_brand(message: Message, state: FSMContext):
    brand = message.text.strip()

    await create_brand_request(
        user_id=message.from_user.id,
        brand=brand
    )

    await message.answer("✅ Бренд відправлено на модерацію")

    # повертаємось назад
    brands = await get_cached_brands(get_brands)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[ADD_BRAND], [BACK]],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


# ================= MODEL =================

@router.message(SellerStates.model)
async def select_model(message: Message, state: FSMContext):
    if not await check_verified(message, state):
        return

    if message.text == "⬅️ Назад":
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[ADD_BRAND], [BACK]],
            resize_keyboard=True
        )

        await state.set_state(SellerStates.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    # ➕ ДОДАТИ МОДЕЛЬ
    if message.text == "➕ Додати модель":
        await state.set_state(SellerStates.add_model)
        await message.answer("✍️ Введи назву моделі:")
        return

    data = await state.get_data()
    brand = data.get("brand")

    models = await get_cached_models(brand, get_models_by_brand)

    if message.text not in models:
        await message.answer("❌ Обери модель з кнопок або додай нову")
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


# ================= ADD MODEL =================

@router.message(SellerStates.add_model)
async def add_model(message: Message, state: FSMContext):
    data = await state.get_data()
    brand = data.get("brand")

    model = message.text.strip()

    await create_model_request(
        user_id=message.from_user.id,
        brand=brand,
        model=model
    )

    await message.answer("✅ Модель відправлено на модерацію")

    models = await get_cached_models(brand, get_models_by_brand)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[ADD_MODEL], [BACK]],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.model)
    await message.answer("🚗 Обери модель:", reply_markup=keyboard)
