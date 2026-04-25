from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import get_car_by_id
from bot.database.repositories.seller_repo import (
    get_seller_by_telegram_id,
    get_garage_info,
    get_active_subscriptions,
    get_seller_cars_by_seller_id,
)

from bot.keyboards.seller_inline import (
    cars_list_kb,
    seller_card_actions_kb
)

from bot.utils.formatters import format_car_card

router = Router()


@router.message(F.text.in_(["📋 Мої авто", "📋 Мій гараж"]))
async def my_cars(message: Message):
    print("🔥 OPEN GARAGE")

    seller = await get_seller_by_telegram_id(message.from_user.id)

    if not seller:
        await message.answer("❌ Продавець не знайдений")
        return

    cars = await get_seller_cars_by_seller_id(seller["id"])

    # ===== 🔥 СТАТИСТИКА ГАРАЖА =====
    garage_info = await get_garage_info(seller["id"])

    total_slots = garage_info.get("total_slots", 0) if garage_info else 0
    used_slots = len(cars)
    free_slots = max(total_slots - used_slots, 0)

    text = (
        "📋 Мій гараж\n\n"
        f"Всього місць: {total_slots}\n"
        f"Зайнято місць: {used_slots}\n"
        f"Вільно місць: {free_slots}\n\n"
        "🚗 Твої авто:"
    )

    await message.answer(text, reply_markup=cars_list_kb(cars))


@router.callback_query(F.data.startswith("car:"))
async def open_car(callback: CallbackQuery, state: FSMContext):
    print("🔥 OPEN CAR:", callback.data)

    car_id = int(callback.data.split(":")[1])
    car = await get_car_by_id(car_id)

    text = format_car_card(car, 1, 1, True)

    await callback.message.answer_photo(
        photo=car.get("photo_id"),
        caption=text,
        reply_markup=seller_card_actions_kb(car_id),
        parse_mode="HTML"
    )
