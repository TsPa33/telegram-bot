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
        "📸 Надішли фото паспорта або ID",
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
        keyboard=[
            [KeyboardButton(text="⬅️ Назад у мій профіль")],
            [KeyboardButton(text="➕ Додати новий бренд")]
        ] + [[KeyboardButton(text=b)] for b in brands],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


# ================= SELECT BRAND =================

@router.message(SellerStates.brand)
async def select_brand(message: Message, state: FSMContext):

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    if message.text == "⬅️ Назад у мій профіль":
        await state.clear()
        await message.answer(
            "🏠 Меню",
            reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False))
        )
        return

    models = await get_cached_models(message.text, get_models_by_brand)

    if not models:
        await message.answer("❌ Моделей не знайдено")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Назад")],
            [KeyboardButton(text="➕ Додати нову модель")]
        ] + [[KeyboardButton(text=m)] for m in models],
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
            keyboard=[[KeyboardButton(text=b)] for b in brands],
            resize_keyboard=True
        )

        await state.set_state(SellerStates.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
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

@router.message(SellerStates.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)
    await state.set_state(SellerStates.description)

    await message.answer(
        "📝 Напиши кілька слів для опису\n"
        "Покупцям це важливо\n\n"
        "Наприклад:\n"
        "В наявності запчастини двигуна та трансмісії. "
        "Вся інформація на сайті або за телефоном"
    )


@router.message(SellerStates.photo, F.text == "⚠️ Пропустити")
async def skip_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=None)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Напиши кілька слів для опису")


@router.message(SellerStates.photo, F.text == "⬅️ Назад до брендів")
async def back_to_brands(message: Message, state: FSMContext):
    brands = await get_cached_brands(get_brands)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


@router.message(SellerStates.photo)
async def photo_error(message: Message):
    await message.answer("❌ Надішли фото або обери дію")


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
