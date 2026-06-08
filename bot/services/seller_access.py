from aiogram.types import Message

from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.keyboards.seller_menu import seller_menu_kb


async def get_verified_seller_or_warn(message: Message):
    seller = await get_seller_by_telegram_id(message.from_user.id)
    if seller and seller.get("is_verified"):
        return seller

    await message.answer(
        "⏳ <b>Доступ продавця ще не активовано</b>\n\n"
        "Після перевірки профілю вам стане доступна CRM та інструменти продавця.",
        parse_mode="HTML",
        reply_markup=seller_menu_kb(is_verified=False),
    )
    return None
