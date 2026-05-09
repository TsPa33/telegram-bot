import json
import os

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.states.seller_states import SellerSiteStates
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.site_config import merge_with_default
from bot.services.demo_context import clear_preserving_demo_context, resolve_active_seller
from bot.services.storage import upload_image

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


# ================= MEDIA HANDLER =================

@router.message(
    StateFilter(SellerSiteStates.site_banner, SellerSiteStates.site_logo),
    F.photo | F.document
)
async def handle_media(message: Message, state: FSMContext):
    current_state = await state.get_state()

    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await clear_preserving_demo_context(state)
        await message.answer("Сайт не знайдено ❌")
        return

    config = merge_with_default(safe_config(site.get("config_draft")))

    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])
    config.setdefault("header", {})

    # ================= FILE =================

    file_path = None

    # 🔥 1. ПРІОРИТЕТ — DOCUMENT (без стиснення)
    if message.document:
        document = message.document

        if not document.mime_type or not document.mime_type.startswith("image/"):
            await message.answer("Завантажте зображення як файл (PNG/JPG) ❌")
            return

        file = await message.bot.get_file(document.file_id)

        file_path = document.file_name or f"{document.file_id}.png"
        await message.bot.download_file(file.file_path, file_path)

    # ⚠️ 2. FALLBACK — PHOTO (зі стисненням)
    elif message.photo:
        await message.answer("⚠️ Фото стискається Telegram. Краще надсилати як файл для максимальної якості.")

        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)

        file_path = f"{photo.file_id}.jpg"
        await message.bot.download_file(file.file_path, file_path)

    else:
        await message.answer("Надішліть зображення ❌")
        return

    # ================= UPLOAD =================

    image_url = await upload_image(file_path)

    if not image_url or not isinstance(image_url, str):
        try:
            os.remove(file_path)
        except Exception:
            pass

        await message.answer("Помилка завантаження зображення ❌")
        await clear_preserving_demo_context(state)
        return

    # 🧹 cleanup
    try:
        os.remove(file_path)
    except Exception:
        pass

    # ================= LOGIC =================

    if current_state == SellerSiteStates.site_banner.state:
        config["hero"]["banners"].append(image_url)
        await message.answer("Банер додано ✅")

    elif current_state == SellerSiteStates.site_logo.state:
        config["header"]["logo"] = image_url
        await message.answer("Лого збережено ✅")

    await update_site_config(site["id"], config)
    await clear_preserving_demo_context(state)
