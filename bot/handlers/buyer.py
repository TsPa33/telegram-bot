from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from bot.database.db import get_brands, get_models_by_brand, find_by_model
from bot.states.buyer_states import Buyer
from bot.utils.validation import normalize

router = Router()


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
    brand = normalize(message.text)

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
    model = normalize(message.text)

    data = await state.get_data()
    brand = data.get("brand")

    results = find_by_model(brand, model)

    if not results:
        await message.answer("❌ Нічого не знайдено")

        brands = get_brands()
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands],
            resize_keyboard=True
        )

        await message.answer("Обери бренд ще раз:", reply_markup=keyboard)
        await state.set_state(Buyer.brand)
        return

    # ✅ нормалізація для UI
    brand = brand.title()
    model = model.upper()

    # ✅ формуємо красивий текст
    text = ""

    for name, website, phone, photo_id in results:
        text += (
            f"🚗 {brand} {model}\n\n"
            f"🏢 {name}\n"
            f"🌐 {website}\n"
            f"📞 {phone}\n\n"
            f"━━━━━━━━━━━━\n\n"
        )

    # ✅ відправка результату
    await message.answer(text)

    # ✅ кнопка "ще пошук"
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
