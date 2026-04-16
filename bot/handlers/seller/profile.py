from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.base import execute, fetchrow
from bot.database.repositories.seller_repo import (
    get_seller_stats,
    get_seller_rating
)

from bot.states.seller_states import SellerStates
from .verification import check_verified

router = Router()

# 🔥 КНОПКИ МЕНЮ (ВАЖЛИВО)
MENU_BUTTONS = {
    "➕ Додати авто",
    "📋 Мої авто",
    "👤 Профіль",
    "📊 Статистика",
    "🔐 Верифікація"
}


# ================= PROFILE =================

@router.message(F.text == "👤 Профіль")
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

    # onboarding
    if not seller or not seller.get("name"):
        await state.set_state(SellerStates.reg_name)
        await message.answer(
            "👋 Давай заповнимо профіль\n\n"
            "Введи імʼя або '-' щоб пропустити"
        )
        return

    verified = "✅ Верифікований" if seller["is_verified"] else "⚠️ Не верифікований"

    text = (
        f"👤 <b>Профіль продавця</b>\n\n"
        f"🏪 {seller.get('shop_name') or '-'}\n"
        f"👤 {seller.get('name') or '-'}\n"
        f"📞 {seller.get('phone') or '-'}\n"
        f"🌐 {seller.get('website') or '-'}\n"
        f"📍 {seller.get('city') or '-'}\n\n"
        f"{verified}"
    )

    await message.answer(text, parse_mode="HTML")


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
        f"📞 Кліки на телефон: {stats['phone_clicks']}\n"
        f"🌐 Переходи на сайт: {stats['site_clicks']}\n\n"
        f"⭐ Рейтинг: <b>{score}</b>"
    )

    await message.answer(text, parse_mode="HTML")


# ================= EDIT PROFILE =================

@router.message(F.text == "✏️ Редагувати профіль")
async def edit_profile(message: Message, state: FSMContext):
    await state.set_state(SellerStates.reg_name)
    await message.answer("👤 Введи імʼя (або '-'):")


# ================= FSM HANDLERS =================

@router.message(SellerStates.reg_name)
async def set_name(message: Message, state: FSMContext):

    if message.text in MENU_BUTTONS:
        await state.clear()
        await message.answer("❌ Дію скасовано")
        return

    name = None if message.text == "-" else message.text

    await state.update_data(name=name)
    await state.set_state(SellerStates.reg_company)

    await message.answer("🏪 Назва розборки (або '-'):")


@router.message(SellerStates.reg_company)
async def set_company(message: Message, state: FSMContext):

    if message.text in MENU_BUTTONS:
        await state.clear()
        await message.answer("❌ Дію скасовано")
        return

    shop_name = None if message.text == "-" else message.text

    await state.update_data(shop_name=shop_name)
    await state.set_state(SellerStates.reg_phone)

    await message.answer("📞 Телефон (або '-'):")


@router.message(SellerStates.reg_phone)
async def set_phone(message: Message, state: FSMContext):

    if message.text in MENU_BUTTONS:
        await state.clear()
        await message.answer("❌ Дію скасовано")
        return

    phone = None if message.text == "-" else message.text

    await state.update_data(phone=phone)
    await state.set_state(SellerStates.reg_link)

    await message.answer("🌐 Сайт (або '-'):")


@router.message(SellerStates.reg_link)
async def set_link(message: Message, state: FSMContext):

    if message.text in MENU_BUTTONS:
        await state.clear()
        await message.answer("❌ Дію скасовано")
        return

    website = None if message.text == "-" else message.text

    await state.update_data(website=website)
    await state.set_state(SellerStates.reg_city)

    await message.answer("📍 Місто (або '-'):")


@router.message(SellerStates.reg_city)
async def set_city(message: Message, state: FSMContext):

    if message.text in MENU_BUTTONS:
        await state.clear()
        await message.answer("❌ Дію скасовано")
        return

    data = await state.get_data()
    city = None if message.text == "-" else message.text

    await execute("""
        UPDATE sellers
        SET 
            name = $1,
            shop_name = $2,
            phone = $3,
            website = $4,
            city = $5
        WHERE telegram_id = $6
    """,
        data.get("name"),
        data.get("shop_name"),
        data.get("phone"),
        data.get("website"),
        city,
        message.from_user.id
    )

    await state.clear()

    await message.answer(
        "✅ Профіль оновлено\n\n"
        "🔐 Рекомендуємо пройти верифікацію"
    )
