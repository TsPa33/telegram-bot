from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.site_repo import (
    get_site_by_seller,
    update_draft,
    publish_site,
)
from bot.services.demo_context import clear_preserving_demo_context, resolve_active_seller

from bot.services.site_config import (
    merge_with_default,
    validate_site_config,
)
from bot.states.seller_states import SellerSiteStates

router = Router()


# ================= HEADER EDIT =================

@router.callback_query(F.data == "site:edit:header")
async def start_edit_header(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_site":
        await callback.answer()
        return

    await state.set_state(SellerSiteStates.edit_header_title)

    if callback.message:
        await callback.message.answer("Введіть заголовок сайту")

    await callback.answer()


# ================= TOGGLE / ABOUT =================

@router.callback_query(F.data.startswith("site:toggle:"))
async def toggle_site_block(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer()
        return

    block = parts[2]

    data = await state.get_data()
    if data.get("flow") != "seller_site":
        await callback.answer()
        return

    seller = await resolve_active_seller(callback, state)
    if not seller:
        return

    seller_id = seller["id"]

    site = await get_site_by_seller(seller_id)
    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = merge_with_default(site.get("config_draft") or {})

    if block not in config:
        await callback.answer("Unknown block", show_alert=True)
        return

    # ABOUT → редагування тексту
    if block == "about":
        await state.set_state(SellerSiteStates.edit_about_text)

        if callback.message:
            await callback.message.answer("Введіть текст блоку 'Про нас'")

        await callback.answer()
        return

    current = config[block].get("enabled", True)

    if block in {"header", "contacts", "services", "map"} and current:
        await callback.answer("Не можна вимкнути", show_alert=True)
        return

    config[block]["enabled"] = not current

    await update_draft(seller_id, config)

    state_text = "увімкнено" if config[block]["enabled"] else "вимкнено"
    await callback.answer(f"{block}: {state_text}")


# ================= PUBLISH =================

@router.callback_query(F.data == "site:publish")
async def publish_site_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_site":
        await callback.answer()
        return

    seller = await resolve_active_seller(callback, state)
    if not seller:
        return

    seller_id = seller["id"]

    site = await get_site_by_seller(seller_id)
    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    # 🔥 КЛЮЧОВИЙ FIX
    config = merge_with_default(site.get("config_draft") or {})

    if not validate_site_config(config):
        await callback.answer("Заповніть базові блоки", show_alert=True)
        return

    result = await publish_site(seller_id)

    if not result:
        await callback.answer("Помилка публікації", show_alert=True)
        return

    await clear_preserving_demo_context(state)
    await callback.answer("Сайт опубліковано")


# ================= SAVE HEADER =================

@router.message(SellerSiteStates.edit_header_title)
async def save_header_title(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_site":
        return

    seller = await resolve_active_seller(message, state)
    if not seller:
        return

    seller_id = seller["id"]

    title = (message.text or "").strip()

    if not title:
        await message.answer("Заголовок не може бути порожнім")
        return

    title = title[:100]

    site = await get_site_by_seller(seller_id)
    if not site:
        await clear_preserving_demo_context(state)
        await message.answer("Сайт не знайдено")
        return

    config = merge_with_default(site.get("config_draft") or {})
    config["header"]["title"] = title

    await update_draft(seller_id, config)
    await clear_preserving_demo_context(state)

    await message.answer("Заголовок оновлено")


# ================= SAVE ABOUT =================

@router.message(SellerSiteStates.edit_about_text)
async def save_about_text(message: Message, state: FSMContext):
    seller = await resolve_active_seller(message, state)
    if not seller:
        return

    seller_id = seller["id"]

    text = (message.text or "").strip()

    if not text:
        await message.answer("Текст не може бути порожнім")
        return

    site = await get_site_by_seller(seller_id)
    if not site:
        await clear_preserving_demo_context(state)
        return

    config = merge_with_default(site.get("config_draft") or {})

    config["about"]["enabled"] = True
    config["about"]["text"] = text

    await update_draft(seller_id, config)

    await clear_preserving_demo_context(state)
    await message.answer("Блок 'Про нас' оновлено")
