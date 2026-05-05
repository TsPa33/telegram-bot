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


@router.message(F.text == "🌐 Мій сайт")
async def site_menu(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    seller_id = seller["id"]

    await state.clear()

    site = await get_site_by_seller(seller_id)

    # ================= CASE 1: НЕ ОПЛАЧЕНО =================
    if not seller.get("has_site"):
        await message.answer(
            "🌐 Мій сайт\n\n"
            "❌ У вас ще немає сайту\n\n"
            "Отримайте:\n"
            "• власний сайт автошроту\n"
            "• сторінку з вашими авто\n"
            "• контакти для клієнтів\n\n"
            "👇 Спочатку оплатіть послугу"
        )
        return

    # ================= CASE 2: ОПЛАЧЕНО, АЛЕ НЕ СТВОРЕНО =================
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

        await message.answer(
            "⚠️ Оплата отримана\n\n"
            "👇 Натисніть щоб створити сайт"
        )
        return

    # ================= CASE 3: ГОТОВО =================

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
