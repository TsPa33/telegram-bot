from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.site_repo import (
    get_site_by_seller,
    create_site,
    subdomain_exists,
)
from bot.services.site_config import get_default_site_config
from bot.services.seller_identity import resolve_seller
from bot.utils.subdomain import generate_unique_subdomain
from bot.keyboards.seller_menu import site_menu_kb

router = Router()


def site_enabled(user_id: int) -> bool:
    return user_id == 6206952389  # можна прибрати пізніше


@router.message(F.text == "🌐 Мій сайт")
async def site_menu(message: Message, state: FSMContext):
    user = message.from_user

    if not user or not site_enabled(user.id):
        return

    # ✅ FIX: централізований seller
    seller = await resolve_seller(message)
    seller_id = seller["id"]

    await state.clear()
    await state.update_data(flow="seller_site")

    site = await get_site_by_seller(seller_id)

    # ✅ CREATE SITE IF NOT EXISTS
    if not site:
        subdomain = await generate_unique_subdomain(
            base=f"user{seller_id}",
            exists_func=subdomain_exists,
        )

        config = get_default_site_config()

        site = await create_site(
            seller_id=seller_id,
            subdomain=subdomain,
            config=config,
        )

    subdomain = site["subdomain"]
    status = site.get("status", "active")

    await message.answer(
        "🌐 Мій сайт\n\n"
        f"Домен: {subdomain}\n"
        f"Статус: {status}",
        reply_markup=site_menu_kb(
            subdomain=subdomain,
            is_active=(status == "active"),
        ),
    )
