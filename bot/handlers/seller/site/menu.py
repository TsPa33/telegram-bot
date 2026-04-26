from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.site_repo import get_site_by_seller, create_site
from bot.services.site_config import get_default_site_config

router = Router()


# TEMP FEATURE FLAG (тільки для тебе)
def site_enabled(user_id: int) -> bool:
    return user_id == 6206952389  # заміни на свій ID


@router.message(F.text == "🌐 Мій сайт")
async def site_menu(message: Message, state: FSMContext):
    if not message.from_user or not site_enabled(message.from_user.id):
        return

    seller_id = message.from_user.id

    await state.clear()
    await state.update_data(flow="seller_site")

    site = await get_site_by_seller(seller_id)

    if not site:
        subdomain = f"user{seller_id}"
        default_config = get_default_site_config()
        await create_site(
            seller_id=seller_id,
            subdomain=subdomain,
            config=default_config,
        )

    await message.answer("🌐 Мій сайт")
