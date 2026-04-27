from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.site_repo import get_site_by_seller, update_site_config

router = Router()


@router.message(F.text == "🖼 Лого")
async def set_logo(message: Message, state: FSMContext):
    await state.set_state("site_logo")
    await message.answer("Надішліть фото логотипу")


@router.message(F.photo)
async def save_logo(message: Message, state: FSMContext):
    if await state.get_state() != "site_logo":
        return

    photo = message.photo[-1].file_id

    site = await get_site_by_seller(message.from_user.id)

    config = site["config"]
    config["header"]["logo"] = photo

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Лого збережено")
