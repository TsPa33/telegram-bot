from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.site_config import merge_with_default

router = Router()

_ALLOWED_MODULES = {"services", "cars", "contacts", "map"}


@router.callback_query(F.data.startswith("module:toggle:"))
async def toggle_site_module(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return

    module_name = parts[2]

    if module_name not in _ALLOWED_MODULES:
        await callback.answer("Невідомий модуль", show_alert=True)
        return

    user = callback.from_user
    if not user:
        await callback.answer()
        return

    seller = await get_seller_by_telegram_id(user.id)
    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = merge_with_default(site.get("config_draft") or {})
    modules = config.setdefault("modules", {})

    # TOGGLE (atomic-like behavior)
    current = bool(modules.get(module_name, True))
    new_value = not current
    modules[module_name] = new_value

    updated = await update_site_config(site["id"], config)
    if not updated:
        await callback.answer("Помилка збереження", show_alert=True)
        return

    # UX: чіткий стан
    state_text = "ON" if new_value else "OFF"

    await callback.answer(f"{module_name}: {state_text}")
