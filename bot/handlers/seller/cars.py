from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import (
    get_seller_cars,
    get_car_by_id
)

from bot.database.repositories.seller_repo import (
    delete_car
)

from bot.keyboards.seller_inline import (
    cars_list_kb,
    seller_card_actions_kb
)

from bot.utils.formatters import format_car_card
from bot.states.seller_states import SellerStates


router = Router()


# ================= MY CARS =================

@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message):
    cars = await get_seller_cars(message.from_user.id)

    if not cars:
        await message.answer("😕 У тебе ще немає авто")
        return

    # 🔴 ДОДАЄМО СТАТИСТИКУ В СПИСОК
    text = "📋 <b>Твої авто:</b>\n\n"

    for car in cars:
        text += (
            f"🚗 <b>{car['brand']} {car['model']}</b>\n"
            f"📝 {car.get('description') or '-'}\n"
            f"👁 Перегляди: {car.get('views', 0)}\n"
            f"📞 Дзвінки: {car.get('phone_clicks', 0)}\n"
            f"🌐 Переходи: {car.get('site_clicks', 0)}\n\n"
        )

    await message.answer(
        text,
        reply_markup=cars_list_kb(cars),
        parse_mode="HTML"
    )


# ================= OPEN CAR =================

@router.callback_query(F.data.startswith("car:"))
async def open_car(callback: CallbackQuery):
    try:
        car_id = int(callback.data.split(":")[1])
    except:
        await callback.answer("Помилка")
        return

    car = await get_car_by_id(car_id)

    if not car:
        await callback.answer("Не знайдено")
        return

    text = format_car_card(car, 0, 1)

    # 🔴 ДОДАЄМО СТАТИСТИКУ В КАРТКУ
    stats = (
        f"\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👁 Перегляди: {car.get('views', 0)}\n"
        f"📞 Дзвінки: {car.get('phone_clicks', 0)}\n"
        f"🌐 Переходи: {car.get('site_clicks', 0)}"
    )

    text += stats

    photo_id = car.get("photo_id")

    if photo_id:
        await callback.message.answer_photo(
            photo=photo_id,
            caption=text,
            reply_markup=seller_card_actions_kb(car_id),
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=seller_card_actions_kb(car_id),
            parse_mode="HTML"
        )

    await callback.answer()


# ================= EDIT CAR =================

@router.callback_query(F.data.startswith("edit:"))
async def edit_car(callback: CallbackQuery, state: FSMContext):
    try:
        car_id = int(callback.data.split(":")[1])
    except:
        await callback.answer("Помилка")
        return

    await state.update_data(car_id=car_id)
    await state.set_state(SellerStates.description)

    await callback.message.answer(
        "✏️ Введи новий опис\n\n"
        "⚠️ Поки доступно тільки редагування опису"
    )

    await callback.answer()


# ================= DELETE CAR =================

@router.callback_query(F.data.startswith("delete:"))
async def delete_car_handler(callback: CallbackQuery):
    try:
        car_id = int(callback.data.split(":")[1])
    except:
        await callback.answer("Помилка")
        return

    await delete_car(car_id, callback.from_user.id)

    await callback.message.answer("🗑 Авто видалено")
    await callback.answer()
    
    # ================= SELLER CARS =================

async def get_seller_cars(telegram_id: int):
    return await fetch(f"""
        {BASE_SELECT}
        WHERE s.telegram_id = $1
        ORDER BY sc.id DESC
        LIMIT 20
    """, telegram_id)
