import json

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.seller_states import SellerSiteStates
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.site_config import merge_with_default
from bot.services.seller_identity import resolve_seller, resolve_seller_from_user

router = Router()


# ================= HELPERS =================

def safe_config(raw):
    if not raw:
        return {}

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}

    return dict(raw)


async def get_context(callback: CallbackQuery):
    seller = await resolve_seller_from_user(callback.from_user)
    if not seller:
        return None, None

    site = await get_site_by_seller(seller["id"])
    return seller, site

# ================= CONTACTS =================

@router.callback_query(F.data == "site:contacts:phone")
async def edit_phone(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_phone)
    await callback.message.answer("Введи телефон")
    await callback.answer()


@router.message(SellerSiteStates.site_contact_phone)
async def save_phone(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await message.answer("Сайт не знайдено ❌")
        return

    config = merge_with_default(safe_config(site.get("config_draft")))

    config.setdefault("contacts", {})
    config["contacts"]["phone"] = message.text

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Телефон збережено ✅")


@router.message(SellerSiteStates.site_contact_address)
async def save_address(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await message.answer("Сайт не знайдено ❌")
        return

    config = merge_with_default(safe_config(site.get("config_draft")))

    config.setdefault("contacts", {})
    config["contacts"]["address"] = message.text

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Адресу збережено ✅")


@router.message(SellerSiteStates.site_contact_map)
async def save_map(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await message.answer("Сайт не знайдено ❌")
        return

    config = merge_with_default(safe_config(site.get("config_draft")))

    config.setdefault("contacts", {})
    config["contacts"]["map_embed"] = message.text

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Мапу збережено ✅")


# ================= BANNERS =================

# 👉 ВХІД В FLOW (КРИТИЧНО)
@router.callback_query(F.data == "site:edit:banners")
async def add_banner(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_banner)
    await callback.message.answer("📤 Надішли фото банера")
    await callback.answer()


# список
@router.callback_query(F.data == "site:banners:list")
async def banners_list(callback: CallbackQuery):
    seller, site = await get_context(callback)

    if not seller or not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = merge_with_default(safe_config(site.get("config_draft")))
    banners = config.get("hero", {}).get("banners", [])

    if not banners:
        await callback.message.answer("Банерів немає")
        return

    for i, banner in enumerate(banners):
        try:
            await callback.message.answer_photo(
                photo=banner,
                caption=f"Банер {i+1}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="❌ Видалити",
                            callback_data=f"site:banners:delete:{i}"
                        )
                    ]]
                )
            )
        except Exception:
            await callback.message.answer(f"{i+1}. {banner}")


# delete
@router.callback_query(F.data.startswith("site:banners:delete:"))
async def banner_delete(callback: CallbackQuery):
    seller = await resolve_seller_from_user(callback.from_user)
    if not seller:
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        return

    config = merge_with_default(safe_config(site.get("config_draft")))
    banners = config.get("hero", {}).get("banners", [])

    index = int(callback.data.split(":")[-1])

    if index >= len(banners):
        await callback.answer("Помилка")
        return

    banners.pop(index)

    await update_site_config(site["id"], config)

    await callback.answer("Банер видалено")
