from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.site_repo import (
    get_site_by_seller,
    create_site,
    subdomain_exists,
)
from bot.services.demo_context import (
    clear_preserving_demo_context,
    is_demo_mode,
    resolve_active_seller,
)
from bot.services.site_config import get_default_site_config
from bot.utils.subdomain import generate_unique_subdomain
from bot.keyboards.seller_menu import site_menu_kb
from bot.keyboards.admin_inline import site_packages_kb
from bot.services.site_packages import format_site_packages_text

router = Router()


@router.message(F.text == "🌐 Мій сайт")
async def site_menu(message: Message, state: FSMContext):
    seller = await resolve_active_seller(message, state)
    if not seller:
        await message.answer("Продавця не знайдено")
        return

    seller_id = seller["id"]
    demo_mode = await is_demo_mode(state)

    await clear_preserving_demo_context(state)
    await state.update_data(flow="seller_site")

    site = await get_site_by_seller(seller_id)

    # ================= CASE 1: НЕ ОПЛАЧЕНО =================
    if not demo_mode and not seller.get("has_site"):
        await message.answer(
            "🌐 <b>Мій сайт</b>\n\n"
            "❌ У вас ще немає сайту\n\n"
            "Отримайте:\n"
            "• власний сайт автошроту\n"
            "• сторінку з вашими авто\n"
            "• контакти для клієнтів\n\n"
            f"{format_site_packages_text()}",
            parse_mode="HTML",
            reply_markup=site_packages_kb(),
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
            demo_mode=demo_mode,
        ),
    )
