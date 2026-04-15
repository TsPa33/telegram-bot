from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.base import execute, fetchrow
from bot.database.repositories.seller_repo import get_or_create_seller

from bot.states.seller_states import SellerStates


router = Router()


# ================= PROFILE =================

@router.message(F.text == "👤 Профіль")
async def show_profile(message: Message):
    seller = await fetchrow("""
        SELECT 
            name,
            shop_name,
            phone,
            website,
            city,
            is_verified,
            verification_status
        FROM sellers
        WHERE telegram_id = $1
    """, message.from_user.id)

    if not seller:
        await message.answer("❌ Профіль не знайдено")
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


# ================= START VERIFICATION =================

@router.message(F.text == "🔐 Верифікація")
async def start_verification(message: Message, state: FSMContext):
    await state.set_state(SellerStates.verification_passport)

    await message.answer(
        "📸 Надішли фото паспорту\n\n"
        "⚠️ Дані використовуються тільки для перевірки"
    )


# ================= HANDLE PASSPORT =================

@router.message(SellerStates.verification_passport, F.photo)
async def handle_passport(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id

    await execute("""
        UPDATE sellers
        SET passport_photo_id = $1,
            verification_status = 'review'
        WHERE telegram_id = $2
    """, photo_id, message.from_user.id)

    await state.clear()

    await message.answer(
        "✅ Документ відправлено на перевірку\n"
        "⏳ Очікуй підтвердження"
    )


# ================= INVALID INPUT =================

@router.message(SellerStates.verification_passport)
async def invalid_passport(message: Message):
    await message.answer("❌ Надішли фото паспорту")


# ================= SIMPLE PROFILE EDIT =================

@router.message(F.text == "✏️ Редагувати профіль")
async def edit_profile(message: Message, state: FSMContext):
    await state.set_state(SellerStates.reg_name)
    await message.answer("👤 Введи імʼя контактної особи:")


@router.message(SellerStates.reg_name)
async def set_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(SellerStates.reg_company)
    await message.answer("🏪 Введи назву магазину:")


@router.message(SellerStates.reg_company)
async def set_company(message: Message, state: FSMContext):
    await state.update_data(shop_name=message.text)
    await state.set_state(SellerStates.reg_phone)
    await message.answer("📞 Введи номер телефону (+380...):")


@router.message(SellerStates.reg_phone)
async def set_phone(message: Message, state: FSMContext):
    phone = message.text.strip()

    if not phone.startswith("+"):
        await message.answer("❌ Номер має починатись з +")
        return

    await state.update_data(phone=phone)
    await state.set_state(SellerStates.reg_link)
    await message.answer("🌐 Введи сайт (або -):")


@router.message(SellerStates.reg_link)
async def set_link(message: Message, state: FSMContext):
    website = None if message.text == "-" else message.text

    await state.update_data(website=website)
    await state.set_state(SellerStates.reg_city)
    await message.answer("📍 Введи місто:")


@router.message(SellerStates.reg_city)
async def set_city(message: Message, state: FSMContext):
    data = await state.get_data()

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
        message.text,
        message.from_user.id
    )

    await state.clear()

    await message.answer("✅ Профіль оновлено")
