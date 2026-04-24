from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import get_car_by_id
from bot.database.repositories.seller_repo import (
    get_seller_by_telegram_id,   # ✅ змінено
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


router = Router()


# ================= MY GARAGE =================

@router.message(F.text.in_(["📋 Мої авто", "📋 Мій гараж"]))
async def my_cars(message: Message):
    # ❌ було: get_or_create_seller
    # ✅ тепер тільки читання
    seller = await get_seller_by_telegram_id(message.from_user.id)

    if not seller:
        await message.answer("❌ Продавець не знайдений")
        return

    seller_id = seller["id"]

    cars = await get_seller_cars_by_seller_id(seller_id)
    garage = await get_garage_info(seller_id)
    subs = await get_active_subscriptions(seller_id)

    text = "📋 <b>Твій гараж</b>\n\n"

    # ===== ГАРАЖ =====
    text += (
        f"🚗 <b>Авто:</b> {garage['used']} / {garage['total']}\n"
        f" <b>Вільно місць:</b> {garage['free']}\n\n"
    )

    # ===== ПІДПИСКИ =====
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

    # ===== ЯКЩО НЕМАЄ АВТО =====
    if not cars:
        text += "😕 У тебе ще немає авто"
        await message.answer(text, parse_mode="HTML")
        return

    # ===== СПИСОК АВТО =====
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
