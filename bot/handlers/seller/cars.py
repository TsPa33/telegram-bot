from aiogram import Router, F
from aiogram.types import Message
from bot.database.repositories.seller_repo import (
    get_seller_by_telegram_id,
    get_garage_info,
    get_active_subscriptions,
    get_seller_cars_by_seller_id,
)
from bot.keyboards.seller_inline import cars_list_kb
from bot.config import DEFAULT_LOGO

router = Router()


@router.message(F.text.in_(["📋 Мої авто", "📋 Мій гараж"]))
async def my_cars(message: Message):
    seller = await get_seller_by_telegram_id(message.from_user.id)

    if not seller:
        await message.answer("❌ Продавець не знайдений")
        return

    seller_id = seller["id"]

    seller_logo = seller.get("logo_url")

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

        photo = seller_logo or DEFAULT_LOGO
        await message.answer_photo(photo=photo)
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

    first_car = cars[0]

    photo = (
        first_car.get("photo_id")
        or seller_logo
        or DEFAULT_LOGO
    )

    await message.answer_photo(photo=photo)

    await message.answer(
        text,
        reply_markup=cars_list_kb(cars),
        parse_mode="HTML"
    )
