from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards.seller_inline import profile_edit_kb

from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    update_seller_field
)

from bot.states.seller_states import SellerStates


router = Router()


# ================= PROFILE =================

@router.message(F.text == "👤 Профіль")
async def seller_profile(message: Message, state: FSMContext):
    await state.clear()

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    text = (
        f"🏪 <b>{seller.get('shop_name') or 'Без назви'}</b>\n\n"
        f"👤 {seller.get('name') or 'Не вказано'}\n"
        f"📞 {seller.get('phone') or '-'}\n"
        f"🌐 {seller.get('website') or '-'}\n"
        f"📍 {seller.get('city') or '-'}\n\n"
        f"📝 <b>Опис:</b>\n"
        f"{seller.get('description') or 'немає'}"
    )

    await message.answer(
        text,
        reply_markup=profile_edit_kb(),
        parse_mode="HTML"
    )


# ================= EDIT PROFILE =================

FIELD_LABELS = {
    "shop_name": "назву розборки",
    "name": "ім’я",
    "phone": "телефон",
    "website": "сайт",
    "city": "місто",
    "description": "опис"
}

MENU_BUTTONS = {
    "📋 Мої авто",
    "➕ Додати авто",
    "👤 Профіль",
    "⬅️ Назад"
}


@router.callback_query(F.data.startswith("profile:"))
async def edit_profile(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":")[1]

    await state.update_data(edit_field=field)
    await state.set_state(SellerStates.edit_profile)

    label = FIELD_LABELS.get(field, field)

    await callback.message.answer(
        f"✏️ Введи {label}\n\nабо '-' щоб очистити"
    )

    await callback.answer()


# ================= SAVE PROFILE =================

@router.message(SellerStates.edit_profile)
async def save_profile(message: Message, state: FSMContext):
    if message.text in MENU_BUTTONS:
        await message.answer("❌ Заверши редагування або введи '-'")
        return

    data = await state.get_data()
    field = data.get("edit_field")

    value = None if message.text == "-" else message.text

    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    await update_seller_field(seller["id"], field, value)

    await state.clear()

    await message.answer("✅ Профіль оновлено")
