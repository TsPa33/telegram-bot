from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.filters import StateFilter

from bot.database.base import execute, fetchrow
from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    get_seller_stats
)
from bot.states.seller_states import SellerStates
from bot.keyboards.profile_inline import profile_edit_kb, profile_cancel_kb

router = Router()

PROFILE_FIELDS = {
    "shop_name": "🏪 Назва магазину",
    "name": "👤 Ім’я",
    "phone": "📞 Телефон",
    "website": "🌐 Сайт",
    "city": "📍 Місто",
    "photo": "🖼 Фото",
    "description": "📝 Опис",
}

ALLOWED_FIELDS = set(PROFILE_FIELDS.keys())


# ================= DB =================

async def _get_seller(telegram_id: int, username: str | None):
    await get_or_create_seller(telegram_id=telegram_id, username=username)

    return await fetchrow(
        """
        SELECT id, shop_name, name, phone, website, city, description, photo_id, is_verified
        FROM sellers WHERE telegram_id = $1
        """,
        telegram_id,
    )


# ================= RENDER =================

def render_profile(seller):
    verified = seller.get("is_verified")

    status = "✅ Верифіковано" if verified else "❌ Не верифіковано"

    return (
        "👤 <b>Профіль продавця</b>\n\n"
        f"🔐 {status}\n\n"
        f"🏪 {seller.get('shop_name') or '-'}\n"
        f"👤 {seller.get('name') or '-'}\n"
        f"📞 {seller.get('phone') or '-'}\n"
        f"🌐 {seller.get('website') or '-'}\n"
        f"📍 {seller.get('city') or '-'}\n"
        f"📝 {seller.get('description') or '-'}\n"
        f"🖼 {'✅' if seller.get('photo_id') else '❌'}"
    )


# ================= SHOW PROFILE =================

@router.message(F.text.in_(["👤 Профіль", "👤 Мій профіль"]))
async def show_profile(message: Message, state: FSMContext):
    await state.clear()

    seller = await _get_seller(message.from_user.id, message.from_user.username)

    await message.answer(
        render_profile(seller),
        parse_mode="HTML",
        reply_markup=profile_edit_kb()
    )


# ================= 📊 STATS =================

@router.message(F.text == "📊 Статистика")
async def seller_stats(message: Message):
    stats = await get_seller_stats(message.from_user.id)

    total_cars = stats.get("total_cars", 0)
    views = stats.get("total_views", 0)
    phone = stats.get("phone_clicks", 0)
    site = stats.get("site_clicks", 0)

    text = (
        "📊 Статистика продавця\n\n"
        f"Оголошень: {total_cars}\n"
        f"Всього переглядів 👁 {views}\n"
        f"Всього дзвінків 📞 {phone}\n"
        f"Всього переходів 🌐 {site}"
    )

    await message.answer(text)


# ================= EDIT CLICK =================

@router.callback_query(F.data.startswith("edit:"))
async def edit_profile(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    field = callback.data.split(":")[1]

    if field in ["cancel", "back"]:
        await state.clear()

        seller = await _get_seller(
            callback.from_user.id,
            callback.from_user.username
        )

        await callback.message.answer(
            render_profile(seller),
            parse_mode="HTML",
            reply_markup=profile_edit_kb()
        )
        return

    if field not in PROFILE_FIELDS:
        return

    await state.set_state(SellerStates.edit_profile)
    await state.update_data(editing_field=field)

    if field == "photo":
        await callback.message.edit_text(
            "📸 Надішліть фото",
            reply_markup=profile_cancel_kb()
        )
    else:
        await callback.message.edit_text(
            f"✍️ Введіть {PROFILE_FIELDS[field]}",
            reply_markup=profile_cancel_kb()
        )


# ================= HANDLE PHOTO =================

@router.message(F.photo, StateFilter(SellerStates.edit_profile))
async def handle_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("editing_field")

    if field != "photo":
        return

    value = message.photo[-1].file_id

    await execute(
        "UPDATE sellers SET photo_id = $1 WHERE telegram_id = $2",
        value,
        message.from_user.id
    )

    await state.clear()
    await message.answer("✅ Фото оновлено")


# ================= HANDLE TEXT =================

@router.message(F.text, StateFilter(SellerStates.edit_profile))
async def handle_text(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("editing_field")

    if field not in ALLOWED_FIELDS:
        await state.clear()
        await message.answer("❌ Помилка поля")
        return

    value = message.text.strip()

    if value == "-":
        value = None

    await execute(
        f"UPDATE sellers SET {field} = $1 WHERE telegram_id = $2",
        value,
        message.from_user.id
    )

    await state.clear()

    seller = await _get_seller(
        message.from_user.id,
        message.from_user.username
    )

    await message.answer(
        "✅ Дані оновлено\n\n" + render_profile(seller),
        parse_mode="HTML",
        reply_markup=profile_edit_kb()
    )


# ================= CRM QUICK ACCESS =================

@router.message(F.text == "🧾 Відкрити CRM")
async def open_crm_quick_access(message: Message):
    from bot.handlers.seller.crm import seller_crm_landing

    await seller_crm_landing(message)
