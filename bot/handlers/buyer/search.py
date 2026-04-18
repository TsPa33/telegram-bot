import math

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.database.base import fetch
from bot.database.repositories.car_repo import count_cars
from bot.keyboards.models import model_kb
from bot.states.buyer_states import Buyer

from .pagination import send_card


router = Router()


@router.callback_query(F.data.startswith("buyer:brand:"))
async def select_brand(callback: types.CallbackQuery, state: FSMContext):
    print("BRAND CLICKED:", callback.data)
    print("BRAND HANDLER HIT")
    current_state = await state.get_state()
    print("CURRENT STATE:", current_state)
    await callback.answer()

    try:
        brand_id = int(callback.data.split(":")[-1])
    except Exception:
        await callback.answer("Invalid brand", show_alert=True)
        return
    await state.update_data(brand_id=brand_id)

    models = await fetch(
        "SELECT id, name FROM models WHERE brand_id = $1 ORDER BY name",
        brand_id,
    )

    if not models:
        await callback.message.answer("❌ Моделей немає")
        return

    await state.set_state(Buyer.model)
    await callback.message.answer("🚘 Обери модель", reply_markup=model_kb(models))


@router.callback_query(F.data.startswith("buyer:model:"))
async def select_model(callback: types.CallbackQuery, state: FSMContext):
    print("MODEL HANDLER HIT:", callback.data)

    await callback.answer()

    try:
        model_id = int(callback.data.split(":")[-1])
    except Exception:
        await callback.answer("Invalid model", show_alert=True)
        return

    model = await fetch(
        "SELECT id FROM models WHERE id = $1 LIMIT 1",
        model_id,
    )
    if not model:
        await callback.message.answer("❌ Модель не знайдена")
        return

    total_items = await count_cars(model_id)

    if total_items == 0:
        await callback.message.answer(
            "😕 Немає оголошень для цієї моделі.\n"
            "Спробуй іншу."
        )
        return

    print("CARS FOUND:", total_items)

    limit = 1
    total_pages = max(1, math.ceil(total_items / limit))

    await state.update_data(
        model_id=model_id,
        page=1,
        total=total_pages,
    )

    await callback.message.answer(f"🔎 Знайдено оголошень: {total_items}")
    await send_card(
        callback.message,
        state,
        new_message=True,
        user_id=callback.from_user.id,
    )
    await state.set_state(None)
