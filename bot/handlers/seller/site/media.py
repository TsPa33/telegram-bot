import json
import os

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.site_config import merge_with_default
from bot.services.storage import upload_image
from bot.services.seller_identity import resolve_seller

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

    # ✅ FIX: централізований seller
    seller = await resolve_seller(message)

    site = await get_site_by_seller(seller["id"])
    if not site:
        await state.clear()
        await message.answer("Сайт не знайдено ❌")
        return

    config = merge_with_default(parse_config(site.get("config_draft")))

    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])
    config.setdefault("header", {})

    # 🔥 найкраща якість
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)

    # ✅ SAFE PATH (без /tmp)
    file_path = f"{photo.file_id}.jpg"

    await message.bot.download_file(file.file_path, file_path)

    # ❗ FIX: cloudinary sync
    image_url = upload_image(file_path)

    # cleanup
    try:
        os.remove(file_path)
    except Exception:
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

        updated = await update_site_config(site["id"], config)

        await state.clear()

        if updated:
            await message.answer("Банер додано ✅")
        else:
            await message.answer("Помилка збереження ❌")

        return

    # LOGO
    if current_state == "site_logo":
        config["header"]["logo"] = image_url

        updated = await update_site_config(site["id"], config)

        await state.clear()

        if updated:
            await message.answer("Лого збережено ✅")
        else:
            await message.answer("Помилка збереження ❌")
