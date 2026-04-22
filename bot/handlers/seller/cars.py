from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import (
    get_seller_cars,
    get_car_by_id
)

from bot.database.repositories.seller_repo import (
    delete_car,
    get_or_create_seller,
    get_active_slots,
    get_active_subscriptions,
)

from bot.keyboards.seller_inline import (
    cars_list_kb,
    seller_card_actions_kb
)

from bot.utils.formatters import format_car_card
from bot.states.seller_states import SellerStates


router = Router()


# ================= MY CARS =================

@router.message(F.text.in_(["📋 Мої авто", "📋 Мій гараж"]))
async def my_cars(message: Message):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )
    cars = await get_seller_cars(message.from_user.id)
    available_slots = await get_active_slots(seller["id"])
    active_subscriptions = await get_active_subscriptions(seller["id"])
    used_slots = len(cars)

    if not cars:
        text = (
            "😕 У тебе ще немає авто\n\n"
            f"🚗 Авто: {used_slots} / {available_slots}"
        )

        if active_subscriptions:
            text += "\n\n📦 <b>Активні підписки:</b>\n"
            for item in active_subscriptions:
                text += (
                    f"\nТариф {item['slots']} авто\n"
                    f"додано: {item['created_at'].strftime('%d.%m.%Y')}\n"
                    f"діє до: {item['expires_at'].strftime('%d.%m.%Y')}\n"
                )

        await message.answer(text, parse_mode="HTML")
        return

    text = (
        "📋 <b>Твої авто:</b>\n\n"
        f"🚗 Авто: {used_slots} / {available_slots}\n"
    )

    if active_subscriptions:
        text += "\n📦 <b>Активні підписки:</b>\n"
        for item in active_subscriptions:
            text += (
                f"\nТариф {item['slots']} авто\n"
                f"додано: {item['created_at'].strftime('%d.%m.%Y')}\n"
                f"діє до: {item['expires_at'].strftime('%d.%m.%Y')}\n"
            )

    text += "\n"

    for car in cars:
        text += (
            f"🚗 <b>{car.get('brand', '-')} {car.get('model', '-')}</b>\n"
            f"📝 {car.get('description') or '-'}\n"
            f"👁 {car.get('views', 0)} | 📞 {car.get('phone_clicks', 0)} | 🌐 {car.get('site_clicks', 0)}\n\n"
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
        car_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer("Помилка")
        return

    car = await get_car_by_id(car_id)

    if not car:
        await callback.answer("Не знайдено")
        return

    text = format_car_card(car)

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

@router.callback_query(F.data.startswith("car_edit:"))
async def edit_car(callback: CallbackQuery, state: FSMContext):
    try:
        car_id = int(callback.data.split(":", 1)[1])
    except Exception:
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
        car_id = int(callback.data.split(":", 1)[1])
    except Exception:
        await callback.answer("Помилка")
        return

    await delete_car(car_id, callback.from_user.id)

    await callback.message.answer("🗑 Авто видалено")
    await callback.answer()
