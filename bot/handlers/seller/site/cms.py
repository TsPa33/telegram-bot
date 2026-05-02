import json

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.states.seller_states import SellerSiteStates
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.seller_identity import resolve_seller, resolve_seller_from_user

router = Router()


# ================= HELPERS =================

async def get_context(callback: CallbackQuery):
    seller = await resolve_seller_from_user(callback.from_user)
    if not seller:
        return None, None

    site = await get_site_by_seller(seller["id"])
    return seller, site


# ================= CONTACTS =================

# -------- PHONE --------

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

    await update_site_config(site["id"], {
        "contacts": {
            "phone": message.text
        }
    })

    await state.clear()
    await message.answer("Телефон збережено ✅")


# -------- ADDRESS (FIX) --------

@router.callback_query(F.data == "site:contacts:address")
async def edit_address(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_address)
    await callback.message.answer("Введи адресу")
    await callback.answer()


@router.message(SellerSiteStates.site_contact_address)
async def save_address(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await message.answer("Сайт не знайдено ❌")
        return

    await update_site_config(site["id"], {
        "contacts": {
            "address": message.text
        }
    })

    await state.clear()
    await message.answer("Адресу збережено ✅")


# -------- MAP (FIX) --------

@router.callback_query(F.data == "site:contacts:map")
async def edit_map(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_map)
    await callback.message.answer(
        "Встав iframe Google Maps\n\n"
        "❗ Не посилання, а iframe\n\n"
        "Приклад:\n"
        "<iframe src='https://www.google.com/maps/embed?...'></iframe>"
    )
    await callback.answer()


@router.message(SellerSiteStates.site_contact_map)
async def save_map(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await message.answer("Сайт не знайдено ❌")
        return

    await update_site_config(site["id"], {
        "contacts": {
            "map_embed": message.text
        }
    })

    await state.clear()
    await message.answer("Мапу збережено ✅")


# ================= BANNERS =================

@router.callback_query(F.data == "site:edit:banners")
async def add_banner(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_banner)
    await callback.message.answer("📤 Надішли фото банера")
    await callback.answer()


@router.message(SellerSiteStates.site_banner, F.photo)
async def save_banner(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    if not site:
        return

    file_id = message.photo[-1].file_id

    current = site.get("config_draft") or {}
    if isinstance(current, str):
        try:
            current = json.loads(current)
        except:
            current = {}

    banners = current.get("hero", {}).get("banners", [])
    banners.append(file_id)

    await update_site_config(site["id"], {
        "hero": {
            "banners": banners
        }
    })

    await state.clear()
    await message.answer("Банер додано ✅")


@router.callback_query(F.data == "site:banners:list")
async def banners_list(callback: CallbackQuery):
    seller, site = await get_context(callback)

    if not seller or not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = site.get("config_draft") or {}
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except:
            config = {}

    banners = config.get("hero", {}).get("banners", [])

    if not banners:
        await callback.message.answer("Банерів немає")
        return

    for i, banner in enumerate(banners):
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


@router.callback_query(F.data.startswith("site:banners:delete:"))
async def banner_delete(callback: CallbackQuery):
    seller = await resolve_seller_from_user(callback.from_user)
    if not seller:
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        return

    config = site.get("config_draft") or {}
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except:
            config = {}

    banners = config.get("hero", {}).get("banners", [])

    index = int(callback.data.split(":")[-1])

    if index >= len(banners):
        await callback.answer("Помилка")
        return

    banners.pop(index)

    await update_site_config(site["id"], {
        "hero": {
            "banners": banners
        }
    })

    await callback.answer("Банер видалено")
