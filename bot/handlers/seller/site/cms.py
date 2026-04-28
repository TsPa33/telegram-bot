import json

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.states.seller_states import SellerSiteStates
from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.database.repositories.service_repo import (
    create_service,
    get_services_by_seller,
    delete_service_by_seller,
)
from bot.database.repositories.car_repo import (
    create_seller_car,
    get_cars_by_seller,
    delete_seller_car,
)
from bot.services.site_config import merge_with_default

router = Router()


# ================= HELPERS =================

def safe_config(raw):
    if not raw:
        return {}

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except:
            return {}

    return dict(raw)


async def get_context(callback: CallbackQuery):
    seller = await get_seller_by_telegram_id(callback.from_user.id)
    if not seller:
        return None, None

    site = await get_site_by_seller(seller["id"])
    return seller, site


# ================= SERVICES =================

@router.callback_query(F.data == "site:services:add")
async def service_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_service_create)
    await callback.message.answer("Введи назву послуги")
    await callback.answer()


@router.message(SellerSiteStates.site_service_create)
async def service_create_process(message: Message, state: FSMContext):
    seller = await get_seller_by_telegram_id(message.from_user.id)

    await create_service(
        seller_id=seller["id"],
        category="default",
        title=message.text,
        city="",
        address="",
        description=None,
        website=None,
        photo_id=None,
    )

    await state.clear()
    await message.answer("Послугу створено ✅")


# ================= CONTACTS =================

@router.callback_query(F.data == "site:contacts:phone")
async def edit_phone(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_phone)
    await callback.message.answer("Введи телефон")
    await callback.answer()


@router.message(SellerSiteStates.site_contact_phone)
async def save_phone(message: Message, state: FSMContext):
    seller = await get_seller_by_telegram_id(message.from_user.id)
    site = await get_site_by_seller(seller["id"])

    config = safe_config(site.get("config_draft"))
    config = merge_with_default(config)

    config.setdefault("contacts", {})
    config["contacts"]["phone"] = message.text

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Телефон збережено ✅")


@router.message(SellerSiteStates.site_contact_address)
async def save_address(message: Message, state: FSMContext):
    seller = await get_seller_by_telegram_id(message.from_user.id)
    site = await get_site_by_seller(seller["id"])

    config = safe_config(site.get("config_draft"))
    config = merge_with_default(config)

    config.setdefault("contacts", {})
    config["contacts"]["address"] = message.text

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Адресу збережено ✅")


@router.message(SellerSiteStates.site_contact_map)
async def save_map(message: Message, state: FSMContext):
    seller = await get_seller_by_telegram_id(message.from_user.id)
    site = await get_site_by_seller(seller["id"])

    config = safe_config(site.get("config_draft"))
    config = merge_with_default(config)

    config.setdefault("contacts", {})
    config["contacts"]["map_embed"] = message.text

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Мапу збережено ✅")
    # ================= BANNERS =================

@router.callback_query(F.data == "site:banners:list")
async def banners_list(callback: CallbackQuery):
    seller, site = await get_context(callback)

    config = site.get("config_draft") or {}
    config = merge_with_default(config)

    banners = config.get("hero", {}).get("banners", [])

    if not banners:
        await callback.message.answer("Банерів немає")
        return

    text = "📋 Банери:\n\n"

    for i, b in enumerate(banners):
        text += f"{i + 1}. {b}\n"

    # кнопки delete
    buttons = []
    for i in range(len(banners)):
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ Видалити {i+1}",
                callback_data=f"site:banners:delete:{i}"
            )
        ])

    await callback.message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
