from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.base import execute, fetchrow
from bot.database.repositories.seller_repo import get_or_create_seller
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


async def _get_seller(telegram_id: int, username: str | None):
    await get_or_create_seller(telegram_id=telegram_id, username=username)

    return await fetchrow(
        """
        SELECT
            id,
            shop_name,
            name,
            phone,
            website,
            city,
            description,
            photo_id,
            is_verified
        FROM sellers
        WHERE telegram_id = $1
        """,
        telegram_id,
    )


async def _render_profile_text(seller) -> str:
    verification_status = (
        "✅ Верифікований" if seller.get("is_verified") else "❌ Не верифікований"
    )

    return (
        "👤 <b>Профіль продавця</b>\n\n"
        f"🏪 {seller.get('shop_name') or '-'}\n"
        f"👤 {seller.get('name') or '-'}\n"
        f"📞 {seller.get('phone') or '-'}\n"
        f"🌐 {seller.get('website') or '-'}\n"
        f"📍 {seller.get('city') or '-'}\n"
        f"📝 {seller.get('description') or '-'}\n"
        f"🖼 {'✅ Додано' if seller.get('photo_id') else '❌ Немає'}\n\n"
        f"{verification_status}"
    )


async def _show_profile_view(
    message: Message | None = None,
    callback: CallbackQuery | None = None,
    telegram_id: int | None = None,
    username: str | None = None,
):
    seller = await _get_seller(telegram_id=telegram_id, username=username)
    text = await _render_profile_text(seller)

    if callback:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=profile_edit_kb(),
        )
        return

    if message:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=profile_edit_kb(),
        )


async def show_profile(message: Message, state: FSMContext):
    await state.clear()

    await _show_profile_view(
        message=message,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )


@router.message(F.text == "👤 Профіль")
async def show_profile_handler(message: Message, state: FSMContext):
    await show_profile(message, state)


@router.callback_query(F.data.startswith("edit:"))
async def handle_edit_callback(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()

    data = callback_query.data
    _, field = data.split(":", 1)

    if field == "back":
        await state.clear()
        await _show_profile_view(
            callback=callback_query,
            telegram_id=callback_query.from_user.id,
            username=callback_query.from_user.username,
        )
        return

    if field == "cancel":
        await state.clear()
        await _show_profile_view(
            callback=callback_query,
            telegram_id=callback_query.from_user.id,
            username=callback_query.from_user.username,
        )
        return

    if field not in PROFILE_FIELDS:
        await callback_query.answer("Невідоме поле", show_alert=True)
        return

    seller = await _get_seller(
        telegram_id=callback_query.from_user.id,
        username=callback_query.from_user.username,
    )

    await state.set_state(SellerStates.edit_profile)
    await state.update_data(
        editing_field=field,
        seller_id=seller["id"],
        profile_chat_id=callback_query.message.chat.id,
        profile_message_id=callback_query.message.message_id,
    )

    prompt = f"Введіть нове значення для {PROFILE_FIELDS[field]}:"
    if field == "photo":
        prompt = "Надішліть нове фото профілю:"

    await callback_query.message.edit_text(
        prompt,
        reply_markup=profile_cancel_kb(),
    )


def _normalize_phone(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit() or ch == "+")


async def handle_profile_input(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("editing_field")

    if not field:
        await state.clear()
        return

    if field == "photo":
        if not message.photo:
            await message.answer("❌ Надішліть фото")
            return

        value = message.photo[-1].file_id
        db_field = "photo_id"
    else:
        if not message.text:
            await message.answer("❌ Введіть текст")
            return

        value = message.text.strip()

        if value == "-":
            value = None

        if field == "phone" and value:
            value = _normalize_phone(value)

        if field == "description" and value and len(value) > 500:
            await message.answer("❌ Опис має бути до 500 символів")
            return

        db_field = field

    await execute(
        f"UPDATE sellers SET {db_field} = $1 WHERE telegram_id = $2",
        value,
        message.from_user.id,
    )

    await state.clear()
    await message.answer("✅ Дані оновлено")

    seller = await _get_seller(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )

    text = await _render_profile_text(seller)

    await message.answer(text, parse_mode="HTML", reply_markup=profile_edit_kb())


@router.message(SellerStates.edit_profile, F.photo)
async def handle_profile_input_photo_handler(message: Message, state: FSMContext):
    await handle_profile_input(message, state)


@router.message(SellerStates.edit_profile)
async def handle_profile_input_text_handler(message: Message, state: FSMContext):
    await handle_profile_input(message, state)