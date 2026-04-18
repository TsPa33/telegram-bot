from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InputMediaPhoto
)

from bot.database.base import fetch
from bot.database.repositories.model_repo import get_brands_with_ids, get_models_by_brand_id
from bot.database.repositories.car_repo import find_cars, count_cars

from bot.states.buyer_states import Buyer

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard
from bot.keyboards.brands import brand_kb
from bot.keyboards.models import model_kb

router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


# ================= START =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()

    brands = await get_brands_with_ids()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    await state.set_state(Buyer.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=brand_kb(brands))


# ================= BRAND =================

@router.callback_query(Buyer.brand, F.data.regexp(r"^brand:\d+$"))
async def select_brand(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    brand_id = int(callback.data.split(":")[1])
    await state.update_data(brand_id=brand_id)

    models = await get_models_by_brand_id(brand_id)

    if not models:
        await callback.message.answer("❌ Моделей немає")
        return

    await state.set_state(Buyer.model)
    await callback.message.answer("🚘 Обери модель:", reply_markup=model_kb(models))


# ================= MODEL =================

@router.callback_query(Buyer.model, F.data.regexp(r"^model:\d+$"))
async def select_model(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    model_id = int(callback.data.split(":")[1])
    model = await fetch(
        """
        SELECT id
        FROM models
        WHERE id = $1
        LIMIT 1
        """,
        model_id
    )
    if not model:
        await callback.message.answer("❌ Модель не знайдена")
        return

    total = await count_cars(model_id)

    if total == 0:
        await callback.message.answer(
            "😕 Поки що немає оголошень для цієї моделі.\n"
            "Спробуй іншу модель або зайди пізніше."
        )
        return

    await state.update_data(
        model_id=model_id,
        page=0,
        total=total
    )

    await callback.message.answer(f"🔎 Знайдено оголошень: {total}")

    await send_card(callback.message, state, new_message=True)

    await state.set_state(None)


# ================= CARD =================

async def send_card(message: types.Message, state: FSMContext, new_message=False):
    data = await state.get_data()

    model_id = data.get("model_id")
    page = data.get("page")
    total = data.get("total")

    if not all([model_id, total is not None]):
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    # 🔥 КЛЮЧОВИЙ ФІКС
    results = await find_cars(model_id, page, limit=1)

    if not results:
        await message.answer("❌ Більше немає результатів")
        return

    car = results[0]

    text = format_car_card(car, page, total)

    keyboard = build_card_keyboard(
        username=car.get("username"),
        page=page,
        total=total
    )

    photo = car.get("photo_id") or DEFAULT_PHOTO

    if new_message:
        await message.answer_photo(
            photo=photo,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        try:
            await message.edit_media(
                InputMediaPhoto(
                    media=photo,
                    caption=text,
                    parse_mode="HTML"
                ),
                reply_markup=keyboard
            )
        except:
            await message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )


# ================= PAGINATION =================

@router.callback_query(F.data.startswith("page:"))
async def paginate(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if not data:
        await callback.answer("Сесія втрачена")
        return

    try:
        page = int(callback.data.split(":")[1])
    except:
        await callback.answer("Помилка")
        return

    total = data.get("total", 0)

    if page < 0 or page >= total:
        await callback.answer("Немає сторінки")
        return

    await state.update_data(page=page)

    await callback.answer()
    await send_card(callback.message, state)


# ================= FALLBACK =================

@router.message(StateFilter(None))
async def fallback(message: types.Message):
    await message.answer("⚠️ Обери дію через меню або введи /find")
