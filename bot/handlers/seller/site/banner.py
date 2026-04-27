from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.site_repo import (
    get_site_by_seller,
    update_site_config,
)
from bot.database.repositories.seller_repo import get_seller_by_telegram_id

router = Router()


@router.message(F.text == "🖼 Банери")
async def set_banner(message: Message, state: FSMContext):
    await state.set_state("site_banner")
    await message.answer("Надішліть фото банера")


@router.message(F.photo)
async def save_banner(message: Message, state: FSMContext):
    if await state.get_state() != "site_banner":
        return

    user = message.from_user
    seller = await get_seller_by_telegram_id(user.id)

    if not seller:
        await message.answer("Продавця не знайдено")
        return

    site = await get_site_by_seller(seller["id"])

    photo = message.photo[-1].file_id

    config = site["config"]

    # 🔥 safety
    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])

    config["hero"]["banners"].append(photo)

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Банер додано ✅")
