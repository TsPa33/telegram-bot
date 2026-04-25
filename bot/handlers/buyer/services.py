from aiogram import Router, F
from aiogram.types import CallbackQuery, Message

from bot.database.repositories.service_repo import get_services_by_filter

router = Router()


# ================= START SERVICES FLOW =================

@router.callback_query(F.data == "buyer:services")
async def start_services(callback: CallbackQuery):
    await callback.answer()

    await callback.message.answer(
        "🔧 Пошук послуг\n\nВведіть місто:"
    )


# ================= CITY INPUT =================

@router.message()
async def services_city_input(message: Message):
    city = message.text.strip()

    services = await get_services_by_filter(city=city, category=None)

    if not services:
        await message.answer("❌ Послуг не знайдено")
        return

    for s in services:
        text = (
            f"🔧 {s['title']}\n"
            f"📍 {s['city']}\n"
            f"📌 {s['address']}\n\n"
            f"{s.get('description') or ''}"
        )

        await message.answer(text)
