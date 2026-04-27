from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.repositories.site_repo import (
    get_site_by_seller,
    update_site_config,
)
from bot.database.repositories.seller_repo import get_seller_by_telegram_id

import json

router = Router()  # 🔥 ОБОВ’ЯЗКОВО


def parse_config(config_raw):
    if isinstance(config_raw, str):
        return json.loads(config_raw)
    return config_raw or {}


@router.callback_query(F.data == "site:edit:logo")
async def set_logo(callback: CallbackQuery, state: FSMContext):
    await state.set_state("site_logo")
    await callback.message.answer("Надішліть логотип")
    await callback.answer()


@router.message(F.photo)
async def save_logo(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state != "site_logo":
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        return

    config = parse_config(site.get("config_draft"))

    config.setdefault("header", {})

    photo = message.photo[-1].file_id
    config["header"]["logo"] = photo

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Лого збережено ✅")
