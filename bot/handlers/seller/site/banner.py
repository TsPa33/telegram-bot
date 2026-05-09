import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.demo_context import resolve_active_seller
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.states.seller_states import SellerSiteStates

router = Router()


def parse_config(config_raw):
    if isinstance(config_raw, str):
        return json.loads(config_raw)
    return config_raw or {}


@router.callback_query(F.data == "site:edit:banners")
async def set_banner(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_banner)
    await callback.message.answer("Надішліть фото банера")
    await callback.answer()


@router.callback_query(F.data == "site:delete:banner")
async def delete_banner_menu(callback: CallbackQuery, state: FSMContext):
    seller = await resolve_active_seller(callback, state)
    if not seller:
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        return

    config = parse_config(site.get("config_draft"))

    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])

    banners = config["hero"]["banners"]

    if not banners:
        await callback.message.answer("Банери відсутні")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Банер #{i + 1}",
                    callback_data=f"site:delete:banner:{i}",
                )
            ]
            for i in range(len(banners))
        ]
    )

    await callback.message.answer(
        "Оберіть банер для видалення:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site:delete:banner:"))
async def delete_banner(callback: CallbackQuery, state: FSMContext):
    seller = await resolve_active_seller(callback, state)
    if not seller:
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        return

    config = parse_config(site.get("config_draft"))

    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])

    index = int(callback.data.split(":")[-1])

    if index >= len(config["hero"]["banners"]):
        return

    config["hero"]["banners"].pop(index)

    await update_site_config(site["id"], config)

    await callback.message.answer("Банер видалено ✅")
    await callback.answer()
