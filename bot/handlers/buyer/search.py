from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from bot.database.repositories.model_repo import get_brands, get_models_by_brand
from bot.utils.cache import get_cached_brands, get_cached_models
from bot.utils.validation import normalize_brand, normalize_model

from bot.states.buyer_states import Buyer

from bot.services.car_service import get_model_or_none
from bot.database.repositories.car_repo import count_cars

from .pagination import send_card

import math


router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


# ================= START =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()

    brands = await get_cached_brands(get_brands)

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
        resize_keyboard=True
    )

    await state.set_state(Buyer.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


# ================= BRAND =================

@router.message(Buyer.brand, F.text != "⬅️ Назад")
async def choose_brand(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()

    brands = await get_cached_brands(get_brands)
    brand = normalize_brand(text)

    if brand not in brands:
        await message.answer("❌ Обери бренд з кнопок")
        return

    models = await get_cached_models(brand, get_models_by_brand)

    if not models:
        await message.answer("❌ Моделей немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
        resize_keyboard=True
    )

    await state.update_data(brand=brand)
    await state.set_state(Buyer.model)

    await message.answer("🚘 Обери модель:", reply_markup=keyboard)


# ================= MODEL =================

@router.message(Buyer.model, F.text != "⬅️ Назад")
async def choose_model(message: types.Message, state: FSMContext):
    try:
        text = (message.text or "").strip()
        model = normalize_model(text)

        data = await state.get_data()
        brand = data.get("brand")

        if not brand:
            await state.clear()
            await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
            return

        models = await get_cached_models(brand, get_models_by_brand)

        if model not in models:
            await message.answer("❌ Обери модель з кнопок")
            return

        model_id = await get_model_or_none(brand, model)

        if not model_id:
            await message.answer("❌ Модель не знайдена")
            return

        total_items = await count_cars(model_id)

        print("MODEL_ID:", model_id)
        print("TOTAL:", total_items)

        if total_items == 0:
            await message.answer(
                "😕 Немає оголошень для цієї моделі.\n"
                "Спробуй іншу."
            )
            return

        # 🔥 PAGE LOGIC
        LIMIT = 1
        total_pages = max(1, math.ceil(total_items / LIMIT))

        await state.update_data(
            model_id=model_id,
            page=1,
            total=total_pages
        )

        await message.answer(f"🔎 Знайдено оголошень: {total_items}")

        await send_card(message, state, new_message=True)

    except Exception as e:
        print("ERROR IN choose_model:", e)
        await message.answer("⚠️ Сталась помилка. Спробуй ще раз.")


# ================= GLOBAL BACK =================

@router.message(F.text == "⬅️ Назад")
async def global_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if not current_state:
        await message.answer("🔙 Головне меню")
        return

    if current_state == Buyer.model:
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(Buyer.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    if current_state == Buyer.brand:
        await state.clear()
        await message.answer("🔙 Головне меню")
        return

    await state.clear()
    await message.answer("🔙 Головне меню")
