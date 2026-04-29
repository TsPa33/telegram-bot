import json
import os

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.states.seller_states import SellerSiteStates
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.site_config import merge_with_default
from bot.services.seller_identity import resolve_seller
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
    F.photo
)
async def handle_media(message: Message, state: FSMContext):
    current_state = await state.get_state()

    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await state.clear()
        await message.answer("Сайт не знайдено ❌")
        return

    config = merge_with_default(safe_config(site.get("config_draft")))

    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])
    config.setdefault("header", {})

    # ================= FILE =================

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)

    file_path = f"{photo.file_id}.jpg"
    await message.bot.download_file(file.file_path, file_path)

    image_url = upload_image(file_path)

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
    await state.clear()
