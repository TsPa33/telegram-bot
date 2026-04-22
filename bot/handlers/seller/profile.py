from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.base import execute, fetchrow
from bot.database.repositories.seller_repo import (
    get_seller_stats,
    get_seller_rating
)

from bot.states.seller_states import SellerStates
from bot.keyboards.seller_inline import profile_edit_kb
from .verification import check_verified

router = Router()


MENU_BUTTONS = {
    "➕ Додати авто",
    "📋 Мої авто",
    "📋 Мій гараж",
    "👤 Профіль",
    "👤 Мій профіль",
    "📊 Статистика",
    "🔐 Верифікація",
    "💳 Пакети послуг",
    "↩️ На головне меню"
}


# ================= 🔥 SAVE PROFILE (ДОДАНО) =================

@router.message(SellerStates.edit_profile)
async def save_profile(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("edit_field")

    value = None if message.text == "-" else message.text

    await execute(
        f"UPDATE sellers SET {field} = $1 WHERE telegram_id = $2",
        value,
        message.from_user.id
    )

    await state.clear()

    await message.answer("✅ Профіль оновлено")


# ================= PROFILE =================

@router.message(F.text.in_(["👤 Профіль", "👤 Мій профіль"]))
async def show_profile(message: Message, state: FSMContext):

    seller = await fetchrow("""
        SELECT 
            name,
            shop_name,
            phone,
            website,
            city,
            is_verified
        FROM sellers
        WHERE telegram_id = $1
    """, message.from_user.id)

    if not seller or not seller.get("name"):
        await state.set_state(SellerStates.reg_name)
        await message.answer(
            "👋 Давай заповнимо профіль\n\n"
            "Введи імʼя або '-' щоб пропустити"
        )
        return

    verified = "✅ Верифікований" if seller["is_verified"] else "⚠️ Не верифікований"

    text = (
        "👤 <b>Профіль продавця</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"🏪 <b>{seller.get('shop_name') or '-'}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"👤 {seller.get('name') or '-'}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"📞 {seller.get('phone') or '-'}\n"
        f"🌐 {seller.get('website') or '-'}\n"
        f"📍 {seller.get('city') or '-'}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"{verified}"
    )

    await message.answer(
        text,
        reply_markup=profile_edit_kb(),
        parse_mode="HTML"
    )


# ================= 🔥 CALLBACK (ДОДАНО) =================

@router.callback_query(F.data.startswith("profile:"))
async def profile_edit_callback(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":")[1]

    await state.update_data(edit_field=field)
    await state.set_state(SellerStates.edit_profile)

    field_map = {
        "name": "👤 Введи ім’я:",
        "shop_name": "🏪 Введи назву:",
        "phone": "📞 Введи телефон:",
        "website": "🌐 Введи сайт:",
        "city": "📍 Введи місто:",
    }

    await callback.message.answer(field_map.get(field, "Введи значення:"))
    await callback.answer()


# ================= 📊 DASHBOARD =================

@router.message(F.text == "📊 Статистика")
async def seller_stats(message: Message, state: FSMContext):

    if not await check_verified(message, state):
        return

    stats = await get_seller_stats(message.from_user.id)
    rating = await get_seller_rating(message.from_user.id)

    if not stats or stats["total_cars"] == 0:
        await message.answer("📭 У тебе ще немає авто")
        return

    score = int(
        (rating["phone"] * 3) +
        (rating["site"] * 2) +
        (rating["views"] * 0.1)
    )

    text = (
        "📊 <b>Моя статистика</b>\n\n"
        f"🚗 Оголошень: {stats['total_cars']}\n"
        f"👀 Перегляди: {stats['total_views']}\n"
        f"📞 Кліки: {stats['phone_clicks']}\n"
        f"🌐 Переходи: {stats['site_clicks']}\n\n"
        f"⭐ Рейтинг: <b>{score}</b>"
    )

    await message.answer(text, parse_mode="HTML")
