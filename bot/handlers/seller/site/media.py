from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database.repositories.site_repo import (
    get_site_by_seller,
    update_site_config,
)
from bot.database.repositories.seller_repo import get_seller_by_telegram_id

import json

router = Router()


def parse_config(config_raw):
    if isinstance(config_raw, str):
        return json.loads(config_raw)
    return config_raw or {}


@router.message(F.photo)
async def handle_media(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state not in ["site_banner", "site_logo"]:
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        return

    config = parse_config(site.get("config_draft"))

    photo = message.photo[-1].file_id

    # 🔥 БАНЕР
    if current_state == "site_banner":
        config.setdefault("hero", {})
        config["hero"].setdefault("banners", [])
        config["hero"]["banners"].append(photo)

        await update_site_config(site["id"], config)
        await message.answer("Банер додано ✅")

    # 🔥 ЛОГО
    elif current_state == "site_logo":
        config.setdefault("header", {})
        config["header"]["logo"] = photo

        await update_site_config(site["id"], config)
        await message.answer("Лого збережено ✅")

    await state.clear()
