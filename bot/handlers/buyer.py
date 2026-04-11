from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.repositories.model_repo import get_brands, get_models_by_brand
from bot.database.repositories.car_repo import find_cars

from bot.states.buyer_states import Buyer
from bot.utils.validation import normalize_brand, normalize_model
from bot.utils.cache import get_cached_brands, get_cached_models

router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


# ================= START =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    brands = await get_cached_brands(get_brands)

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

    models = await get_models_by_brand(brand)

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

    await state.update_data(model=model, page=0)

    await send_results(message, state)


# ================= RESULTS =================

async def send_results(message: types.Message, state: FSMContext):
    data = await state.get_data()

    brand = data.get("brand")
    model = data.get("model")
    page = data.get("page", 0)

    results = await find_cars(brand, model, page)

    if not results:
        await message.answer("❌ Більше немає результатів")
        return

    for row in results:
        username = row["username"]
        brand_db = row["brand"]
        model_db = row["model"]
        photo_id = row["photo_id"]

        username_display = f"@{username}" if username else "без username"

        text = (
            f"🚗 {brand_db} {model_db}\n\n"
            f"👤 Продавець: {username_display}"
        )

        if photo_id:
            await message.answer_photo(photo_id, caption=text)
        else:
            await message.answer_photo(DEFAULT_PHOTO, caption=text)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Ще", callback_data="next_page")]
    ])

    await message.answer("Показати ще?", reply_markup=keyboard)


# ================= PAGINATION =================

@router.callback_query(F.data == "next_page")
async def next_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data.get("page", 0) + 1

    await state.update_data(page=page)

    await callback.answer()
    await send_results(callback.message, state)
