from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.services.demo_context import resolve_active_seller
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.site_config import merge_with_default

router = Router()

_ALLOWED_MODULES = {"services", "cars", "contacts", "map"}


@router.callback_query(F.data.startswith("module:toggle:"))
async def toggle_site_module(callback: CallbackQuery, state: FSMContext):
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return

    module_name = parts[2]

    if module_name not in _ALLOWED_MODULES:
        await callback.answer("Невідомий модуль", show_alert=True)
        return

    seller = await resolve_active_seller(callback, state)
    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    # ✅ беремо повний config тільки для читання
    config = merge_with_default(site.get("config_draft") or {})
    modules = config.get("modules", {})

    default_modules = merge_with_default({})["modules"]

    # нормалізація
    modules = {
        key: bool(modules.get(key, True))
        for key in default_modules
    }

    current = modules.get(module_name, True)
    new_value = not current

    modules[module_name] = new_value

    # 🔥 КРИТИЧНО: передаємо ТІЛЬКИ modules
    updated = await update_site_config(
        site["id"],
        {
            "modules": modules
        }
    )

    if not updated:
        await callback.answer("Помилка збереження", show_alert=True)
        return

    state_text = "ON" if new_value else "OFF"

    await callback.answer(f"{module_name}: {state_text}")
