from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import get_car_by_id
from bot.database.repositories.seller_repo import (
    get_seller_by_telegram_id,
    get_garage_info,
    get_active_subscriptions,
    get_seller_cars_by_seller_id,
    delete_car,
)

from bot.keyboards.seller_inline import (
    cars_list_kb,
    seller_card_actions_kb
)

from bot.utils.formatters import format_car_card
from bot.states.seller_states import SellerStates

print("🔥 OPEN CAR CLICK")
router = Router()


# ================= MY GARAGE =================

@router.message(F.text.in_(["📋 Мої авто", "📋 Мій гараж"]))
async def my_cars(message: Message):
    seller = await get_seller_by_telegram_id(message.from_user.id)

    if not seller:
        await message.answer("❌ Продавець не знайдений")
        return

    seller_id = seller["id"]

    cars = await get_seller_cars_by_seller_id(seller_id)
    garage = await get_garage_info(seller_id)
    subs = await get_active_subscriptions(seller_id)

    text = "📋 <b>Твій гараж</b>\n\n"

    text += (
        f"🚗 <b>Авто:</b> {garage['used']} / {garage['total']}\n"
        f" <b>Вільно місць:</b> {garage['free']}\n\n"
    )

    if subs:
        text += " <b>Активні підписки:</b>\n\n"

        for sub in subs:
            text += (
                f"Тариф {sub['slots']} авто\n"
                f"додано: {sub['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
                f"діє до: {sub['expires_at'].strftime('%d.%m.%Y %H:%M')}\n"
                f"——————————————\n"
            )

        text += "\n"

    if not cars:
        text += "😕 У тебе ще немає авто"
        await message.answer(text, parse_mode="HTML")
        return

    text += "🚗 <b>Список авто:</b>\n\n"

    for car in cars:
        text += (
            f"<b>{car.get('brand', '-')} {car.get('model', '-')}</b>\n"
            f"{car.get('description') or '-'}\n"
            f"👁 {car.get('views', 0)} | 📞 {car.get('phone_clicks', 0)} | 🌐 {car.get('site_clicks', 0)}\n\n"
        )

    await message.answer(
        text,
        reply_markup=cars_list_kb(cars),
        parse_mode="HTML"
    )


# ================= OPEN CAR =================

@router.callback_query(F.data.startswith("car:"))
async def open_car_from_garage(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    try:
        car_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.message.answer("❌ Невірний ідентифікатор авто")
        return

    car = await get_car_by_id(car_id)

    if not car:
        await callback.message.answer("❌ Авто не знайдено")
        return

    text = format_car_card(
        car,
        page=1,
        total=1,
        is_owner=True
    )

    await callback.message.answer_photo(
        photo=car.get("photo_id"),
        caption=text,
        reply_markup=seller_card_actions_kb(car_id),
        parse_mode="HTML"
    )
