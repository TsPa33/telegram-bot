from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from bot.database.repositories.model_repo import get_models_by_brand
from bot.database.repositories.car_repo import count_cars, find_cars

from bot.utils.cache import get_cached_models
from bot.utils.validation import normalize_brand, normalize_model

from bot.states.buyer_states import Buyer

from .pagination import send_card


router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


# ================= BRAND =================

@router.message(Buyer.brand)
async def choose_brand(message: types.Message, state: FSMContext):
    if await state.get_state() != Buyer.brand:
        return

    text = message.text.strip()
    brand = normalize_brand(text)

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

@router.message(Buyer.model)
async def choose_model(message: types.Message, state: FSMContext):
    if await state.get_state() != Buyer.model:
        return

    text = message.text.strip()
    model = normalize_model(text)

    data = await state.get_data()
    brand = data.get("brand")

    if not brand:
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    total = await count_cars(brand, model)

    if total == 0:
        await message.answer(
            "😕 Поки що немає оголошень для цієї моделі.\n"
            "Спробуй іншу модель або зайди пізніше."
        )
        return

    # 🔴 кешуємо результати
    results = await find_cars(brand, model, 0, limit=10)

    if not results:
        await message.answer("❌ Більше немає результатів")
        return

    await state.update_data(
        model=model,
        page=0,
        total=len(results),
        results=results
    )

    await message.answer(f"🔎 Знайдено оголошень: {len(results)}")

    await send_card(message, state, new_message=True)

    # ❌ НЕ ОЧИЩАЄМО STATE


# ================= FALLBACK BRAND =================

@router.message()
async def fallback_brand_handler(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text:
        return

    # пробуємо як бренд
    brand = normalize_brand(text)

    models = await get_cached_models(brand, get_models_by_brand)

    if not models:
        return  # не бренд → нічого не робимо

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
        resize_keyboard=True
    )

    await state.update_data(brand=brand)
    await state.set_state(Buyer.model)

    await message.answer("🚘 Обери модель:", reply_markup=keyboard)
