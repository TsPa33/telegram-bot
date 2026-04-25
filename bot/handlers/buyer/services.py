from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.service_repo import get_services_by_filter

router = Router()


# ================= START SERVICES FLOW =================

@router.callback_query(F.data == "buyer:services")
async def start_services(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    # ставимо прапорець
    await state.update_data(services_search=True)

    await callback.message.answer(
        "🔧 Пошук послуг\n\nВведіть місто:"
    )


# ================= CITY INPUT =================

@router.message()
async def services_city_input(message: Message, state: FSMContext):
    data = await state.get_data()

    # ❗ ФІЛЬТР — щоб не ламати інші handler-и
    if not data.get("services_search"):
        return

    city = message.text.strip()

    services = await get_services_by_filter(city=city, category=None)

    if not services:
        await message.answer("❌ Послуг не знайдено")
        return

    for s in services:
        description = s.get("description") or "Опис відсутній"

        text = (
            f"🔧 {s['title']}\n"
            f"📍 {s['city']}\n"
            f"📌 {s['address']}\n\n"
            f"{description}"
        )

        await message.answer(text)

    # очищаємо після пошуку
    await state.update_data(services_search=False)
