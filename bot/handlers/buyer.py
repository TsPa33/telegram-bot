from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from bot.database.db import get_brands, get_models_by_brand, find_cars
from bot.states.buyer_states import Buyer
from bot.utils.validation import normalize_brand, normalize_model

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"

router = Router()

@router.message(F.photo)
async def debug_file_id(message: types.Message):
    file_id = message.photo[-1].file_id
    print("FILE_ID:", file_id)
    await message.answer(f"FILE_ID:\n{file_id}")
# ================= START FIND =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await message.answer(
        "Оновлюю меню...",
        reply_markup=ReplyKeyboardRemove()
    )

    brands = get_brands()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands],
        resize_keyboard=True
    )

    await message.answer("Обери бренд:", reply_markup=keyboard)
    await state.set_state(Buyer.brand)


# ================= BRAND =================

@router.message(Buyer.brand)
async def choose_brand(message: types.Message, state: FSMContext):
    brand = normalize_brand(message.text)

    models = get_models_by_brand(brand)

    if not models:
        await message.answer("❌ Моделей немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models],
        resize_keyboard=True
    )

    await state.update_data(brand=brand)

    await message.answer("Обери модель:", reply_markup=keyboard)
    await state.set_state(Buyer.model)


# ================= MODEL =================

@router.message(Buyer.model)
async def choose_model(message: types.Message, state: FSMContext):
    model = normalize_model(message.text)

    data = await state.get_data()
    brand = data.get("brand")

    results = find_cars(brand, model)

    if not results:
        await message.answer("❌ Немає оголошень по цьому авто")

        brands = get_brands()
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands],
            resize_keyboard=True
        )

        await message.answer("Обери бренд ще раз:", reply_markup=keyboard)
        await state.set_state(Buyer.brand)
        return

    # 🔥 ВАЖЛИВИЙ БЛОК
    for username, brand_db, model_db, photo_id in results:
        username_display = f"@{username}" if username else "без username"

        text = (
            f"🚗 {brand_db} {model_db}\n\n"
            f"👤 Продавець: {username_display}"
    )

    # 🔥 ГОЛОВНЕ — fallback на заглушку
        if photo_id:
            await message.answer_photo(photo_id, caption=text)
        else:
            await message.answer_photo(DEFAULT_PHOTO, caption=text)

    # кнопка повторного пошуку
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔁 Знайти ще авто")]
        ],
        resize_keyboard=True
    )

    await message.answer("Що далі?", reply_markup=keyboard)
    await state.clear()


# ================= RESTART =================

@router.message(F.text == "🔁 Знайти ще авто")
async def restart_search(message: types.Message, state: FSMContext):
    brands = get_brands()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands],
        resize_keyboard=True
    )

    await message.answer("Обери бренд:", reply_markup=keyboard)
    await state.set_state(Buyer.brand)
