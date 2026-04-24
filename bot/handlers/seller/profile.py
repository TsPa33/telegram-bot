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
        SELECT id, shop_name, name, phone, website, city, description, photo_id, is_verified
        FROM sellers WHERE telegram_id = $1
        """,
        telegram_id,
    )


@router.message(F.text == "👤 Профіль")
async def show_profile(message: Message, state: FSMContext):
    print("🔥 OPEN PROFILE")

    await state.clear()

    seller = await _get_seller(message.from_user.id, message.from_user.username)

    text = f"""
👤 <b>Профіль продавця</b>

🏪 {seller.get('shop_name') or '-'}
👤 {seller.get('name') or '-'}
📞 {seller.get('phone') or '-'}
🌐 {seller.get('website') or '-'}
📍 {seller.get('city') or '-'}
📝 {seller.get('description') or '-'}
🖼 {'✅' if seller.get('photo_id') else '❌'}
"""

    await message.answer(text, parse_mode="HTML", reply_markup=profile_edit_kb())
