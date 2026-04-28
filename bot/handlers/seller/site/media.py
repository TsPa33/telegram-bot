import json
import os

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.site_config import merge_with_default
from bot.services.storage import upload_image

router = Router()

MAX_BANNERS = 10


def parse_config(config_raw):
    if isinstance(config_raw, str):
        try:
            return json.loads(config_raw)
        except Exception:
            return {}
    return config_raw or {}


@router.message(F.photo)
async def handle_media(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state not in ["site_banner", "site_logo"]:
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await state.clear()
        await message.answer("Продавця не знайдено ❌")
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        await state.clear()
        await message.answer("Сайт не знайдено ❌")
        return

    config = merge_with_default(parse_config(site.get("config_draft")))

    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])
    config.setdefault("header", {})

    # 🔥 беремо найкращу якість
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)

    # тимчасовий файл
    file_path = f"/tmp/{photo.file_id}.jpg"

    await message.bot.download_file(file.file_path, file_path)

    # 🔥 upload в cloudinary
    image_url = await upload_image(file_path)

    # очистка
    try:
        os.remove(file_path)
    except:
        pass

    # ================= SAVE =================

    # BANNER
    if current_state == "site_banner":
        banners = config["hero"]["banners"]

        if len(banners) >= MAX_BANNERS:
            await state.clear()
            await message.answer(f"Максимум {MAX_BANNERS} банерів")
            return

        banners.append(image_url)

        await update_site_config(site["id"], config)
        await state.clear()
        await message.answer("Банер додано ✅")
        return

    # LOGO
    if current_state == "site_logo":
        config["header"]["logo"] = image_url

        await update_site_config(site["id"], config)
        await state.clear()
        await message.answer("Лого збережено ✅")
