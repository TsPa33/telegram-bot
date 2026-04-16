from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.keyboards.seller_menu import seller_menu_kb
from bot.keyboards.seller_inline import (
    cars_list_kb,
    seller_card_actions_kb,
    profile_edit_kb
)

from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    delete_car,
    update_description,
    add_seller_car,
    update_seller_field
)

from bot.database.repositories.car_repo import (
    get_seller_cars,
    get_car_by_id
)

from bot.database.repositories.model_repo import (
    get_brands,
    get_models_by_brand,
    get_model_id
)

from bot.database.repositories.admin_repo import create_verification_request

from bot.utils.cache import get_cached_brands, get_cached_models
from bot.utils.formatters import format_car_card

from bot.states.seller_states import SellerStates

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


# ================= 🔐 CHECK VERIFIED =================

async def check_verified(message: Message, state: FSMContext):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    if seller.get("is_verified"):
        return True

    data = await state.get_data()

    if not data.get("verification_warned"):
        await message.answer(
            "🔐 <b>Акаунт не верифікований</b>\n\n"
            "Щоб користуватись ботом — пройди верифікацію",
            parse_mode="HTML"
        )

        await state.update_data(verification_warned=True)

    return False


# ================= 🔐 VERIFICATION =================

@router.message(F.text == "🔐 Верифікація")
async def start_verification(message: Message, state: FSMContext):
    await state.set_state(SellerStates.verification_photo)

    await message.answer(
        "🔐 <b>Верифікація продавця</b>\n\n"
        "📸 Надішли фото паспорта або ID\n\n"
        "⚠️ Дані використовуються лише для перевірки",
        parse_mode="HTML"
    )


@router.message(SellerStates.verification_photo, F.photo)
async def receive_verification_photo(message: Message, state: FSMContext):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    photo_id = message.photo[-1].file_id

    await create_verification_request(
        seller_id=seller["id"],
        photo_id=photo_id
    )

    await message.answer("✅ Заявка відправлена\n⏳ Очікуй підтвердження")

    await state.clear()


@router.message(SellerStates.verification_photo)
async def verification_error(message: Message):
    await message.answer("❌ Надішли фото документа")


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


# ================= SELECT BRAND =================

@router.message(SellerStates.brand)
async def select_brand(message: Message, state: FSMContext):

    if message.text == "⬅️ Назад":
        await state.clear()
        await message.answer("🏠 Меню", reply_markup=seller_menu_kb())
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


# ================= SELECT MODEL =================

@router.message(SellerStates.model)
async def select_model(message: Message, state: FSMContext):

    if message.text == "⬅️ Назад":
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(SellerStates.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    await state.update_data(model=message.text)
    await state.set_state(SellerStates.photo)

    await message.answer("📸 Надішли фото авто:")


# ================= PHOTO =================

@router.message(SellerStates.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Введи опис авто:")


@router.message(SellerStates.photo)
async def photo_error(message: Message):
    await message.answer("❌ Надішли фото або натисни '⬅️ Назад'")


# ================= DESCRIPTION =================

@router.message(SellerStates.description)
async def save_car(message: Message, state: FSMContext):
    data = await state.get_data()

    if data.get("car_id"):
        await update_description(data["car_id"], message.text)
        await message.answer("✅ Опис оновлено")
        await state.clear()
        return

    model_id = await get_model_id(data["brand"], data["model"])

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    await add_seller_car(
        seller_id=seller["id"],
        model_id=model_id,
        photo_id=data.get("photo_id"),
        description=message.text or "Без опису"
    )

    await message.answer("✅ Авто додано")

    await state.clear()


# ================= MY CARS =================

@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message, state: FSMContext):

    if not await check_verified(message, state):
        return

    cars = await get_seller_cars(message.from_user.id)

    if not cars:
        await message.answer("😕 У тебе ще немає авто")
        return

    await message.answer(
        "📋 <b>Твої авто:</b>",
        reply_markup=cars_list_kb(cars),
        parse_mode="HTML"
    )


# ================= PROFILE =================

@router.message(F.text == "👤 Профіль")
async def seller_profile(message: Message, state: FSMContext):

    if not await check_verified(message, state):
        return

    await state.clear()

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    text = (
        f"🏪 <b>{seller.get('shop_name') or 'Без назви'}</b>\n\n"
        f"👤 {seller.get('name') or 'Не вказано'}\n"
        f"📞 {seller.get('phone') or '-'}\n"
        f"🌐 {seller.get('website') or '-'}\n"
        f"📍 {seller.get('city') or '-'}\n\n"
        f"{'✅ Верифікований продавець' if seller.get('is_verified') else '⚠️ Не верифікований'}"
    )

    await message.answer(
        text,
        reply_markup=profile_edit_kb(),
        parse_mode="HTML"
    )


# ================= EDIT PROFILE =================

@router.callback_query(F.data.startswith("profile:"))
async def edit_profile(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":")[1]

    await state.update_data(edit_field=field)
    await state.set_state(SellerStates.edit_profile)

    await callback.message.answer("✏️ Введи нове значення або '-'")
    await callback.answer()


@router.message(SellerStates.edit_profile)
async def save_profile(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("edit_field")

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    value = None if message.text == "-" else message.text

    await update_seller_field(seller["id"], field, value)

    await message.answer("✅ Профіль оновлено")
    await state.clear()
