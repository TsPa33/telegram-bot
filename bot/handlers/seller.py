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

from bot.utils.cache import get_cached_brands, get_cached_models
from bot.utils.formatters import format_car_card

from bot.states.seller_states import SellerStates

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


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
    if message.text == "⬅️ Назад":
        await state.clear()
        await message.answer("🏠 Меню", reply_markup=seller_menu_kb())
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
    if message.text == "⬅️ Назад":
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

@router.message(SellerStates.photo, F.text == "⬅️ Назад")
async def back_to_model(message: Message, state: FSMContext):
    data = await state.get_data()
    brand = data.get("brand")

    models = await get_cached_models(brand, get_models_by_brand)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
        resize_keyboard=True
    )

    await state.set_state(SellerStates.model)
    await message.answer("🚗 Обери модель:", reply_markup=keyboard)


@router.message(SellerStates.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id

    await state.update_data(photo_id=photo_id)
    await state.set_state(SellerStates.description)

    await message.answer("📝 Введи опис:")


@router.message(SellerStates.photo)
async def photo_error(message: Message):
    await message.answer("❌ Надішли саме фото або натисни '⬅️ Назад'")


# ================= DESCRIPTION =================

@router.message(SellerStates.description)
async def save_car(message: Message, state: FSMContext):
    data = await state.get_data()

    # EDIT
    if data.get("car_id"):
        car_id = data["car_id"]

        await update_description(car_id, message.text)
        car = await get_car_by_id(car_id)

        text = format_car_card(car, 0, 1)

        await message.answer_photo(
            photo=car.get("photo_id"),
            caption=text,
            parse_mode="HTML"
        )

        await state.clear()
        return

    # CREATE
    brand = data.get("brand")
    model = data.get("model")
    photo_id = data.get("photo_id")
    description = message.text or "Без опису"

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

    text = format_car_card({
        "brand": brand,
        "model": model,
        "description": description
    }, 0, 1)

    await message.answer_photo(
        photo=photo_id,
        caption=text,
        parse_mode="HTML"
    )

    await state.clear()


# ================= MY CARS =================

@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message):
    cars = await get_seller_cars(message.from_user.id)

    if not cars:
        await message.answer("😕 У тебе ще немає авто")
        return

    await message.answer(
        "📋 <b>Твої авто:</b>",
        reply_markup=cars_list_kb(cars),
        parse_mode="HTML"
    )


# ================= OPEN CAR =================

@router.callback_query(F.data.startswith("car:"))
async def open_car(callback: types.CallbackQuery):
    car_id = int(callback.data.split(":")[1])

    car = await get_car_by_id(car_id)

    if not car:
        await callback.answer("Не знайдено")
        return

    text = format_car_card(car, 0, 1)

    photo_id = car.get("photo_id")

    if photo_id:
        await callback.message.answer_photo(
            photo=photo_id,
            caption=text,
            reply_markup=seller_card_actions_kb(car_id),
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=seller_card_actions_kb(car_id),
            parse_mode="HTML"
        )

    await callback.answer()

# ================= PROFILE =================

@router.message(F.text == "👤 Профіль")
async def seller_profile(message: Message, state: FSMContext):
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
        f"📝 <b>Опис:</b>\n"
        f"{seller.get('description') or 'немає'}"
    )

    await message.answer(
        text,
        reply_markup=profile_edit_kb(),
        parse_mode="HTML"
    )


# ================= EDIT PROFILE =================

FIELD_LABELS = {
    "shop_name": "назву розборки",
    "name": "ім’я",
    "phone": "телефон",
    "website": "сайт",
    "city": "місто",
    "description": "опис"
}

MENU_BUTTONS = {
    "📋 Мої авто",
    "➕ Додати авто",
    "👤 Профіль",
    "⬅️ Назад"
}


@router.callback_query(F.data.startswith("profile:"))
async def edit_profile(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":")[1]

    await state.update_data(edit_field=field)
    await state.set_state(SellerStates.edit_profile)

    await callback.answer()

    label = FIELD_LABELS.get(field, field)

    await callback.message.answer(
        f"✏️ Введи {label}\n\nабо '-' щоб очистити"
    )


@router.message(SellerStates.edit_profile, F.text)
async def save_profile(message: Message, state: FSMContext):
    if message.text in MENU_BUTTONS:
        await message.answer("❌ Заверши редагування або введи '-'")
        return

    data = await state.get_data()
    field = data.get("edit_field")

    value = None if message.text == "-" else message.text

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    await update_seller_field(seller["id"], field, value)

    await state.clear()

    await message.answer("✅ Оновлено")

    await seller_profile(message, state)

# ================= EDIT CAR =================

@router.callback_query(F.data.startswith("edit:"))
async def edit_car(callback: types.CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split(":")[1])

    car = await get_car_by_id(car_id)

    if not car:
        await callback.answer("Не знайдено")
        return

    # зберігаємо car_id для редагування
    await state.update_data(car_id=car_id)

    await state.set_state(SellerStates.description)

    await callback.message.answer("✏️ Введи новий опис:")

    await callback.answer()
