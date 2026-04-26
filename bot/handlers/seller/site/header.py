from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.site_repo import get_site_by_seller, update_draft
from bot.services.site_config import merge_with_default
from bot.states.seller_states import SellerSiteStates

router = Router()


@router.callback_query(F.data == "site:edit:header")
async def start_edit_header(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_site":
        await callback.answer()
        return

    await state.set_state(SellerSiteStates.edit_header_title)
    await callback.message.answer("Введіть заголовок сайту")
    await callback.answer()


@router.message(SellerSiteStates.edit_header_title)
async def save_header_title(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_site":
        return

    site = await get_site_by_seller(message.from_user.id)
    if not site:
        await state.clear()
        await message.answer("Сайт не знайдено")
        return

    config = merge_with_default(site.get("config_draft") or {})
    config["header"]["title"] = message.text or ""

    await update_draft(message.from_user.id, config)
    await state.clear()

    await message.answer("Заголовок оновлено")
