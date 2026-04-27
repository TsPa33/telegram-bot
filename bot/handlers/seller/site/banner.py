from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot.database.repositories.site_repo import (
    get_site_by_seller,
    update_site_config,
)
from bot.database.repositories.seller_repo import get_seller_by_telegram_id

router = Router()


@router.callback_query(F.data == "site:edit:banners")
async def set_banner(callback: CallbackQuery, state: FSMContext):
    await state.set_state("site_banner")
    await callback.message.answer("Надішліть фото банера")
    await callback.answer()


@router.callback_query(F.data == "site:delete:banner")
async def delete_banner_menu(callback: CallbackQuery):
    user = callback.from_user
    seller = await get_seller_by_telegram_id(user.id)

    if not seller:
        await callback.message.answer("Продавця не знайдено")
        await callback.answer()
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        await callback.message.answer("Сайт не знайдено")
        await callback.answer()
        return

    config = site.get("config_draft") or site.get("config") or {}
    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])

    banners = config["hero"]["banners"]
    if not banners:
        await callback.message.answer("Банери відсутні")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Банер #{index + 1}",
                    callback_data=f"site:delete:banner:{index}",
                )
            ]
            for index in range(len(banners))
        ]
    )

    await callback.message.answer("Оберіть банер для видалення:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("site:delete:banner:"))
async def delete_banner(callback: CallbackQuery):
    user = callback.from_user
    seller = await get_seller_by_telegram_id(user.id)

    if not seller:
        await callback.message.answer("Продавця не знайдено")
        await callback.answer()
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        await callback.message.answer("Сайт не знайдено")
        await callback.answer()
        return

    config = site.get("config_draft") or site.get("config") or {}
    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])

    try:
        index = int(callback.data.split(":")[-1])
    except (ValueError, AttributeError):
        await callback.answer("Некоректний індекс", show_alert=True)
        return

    banners = config["hero"]["banners"]
    if index < 0 or index >= len(banners):
        await callback.answer("Банер не знайдено", show_alert=True)
        return

    banners.pop(index)
    await update_site_config(site["id"], config)

    await callback.message.answer("Банер видалено ✅")
    await callback.answer()


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
    if not site:
        await message.answer("Сайт не знайдено")
        return

    photo = message.photo[-1].file_id

    config = site.get("config_draft") or site.get("config") or {}
    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])
    config["hero"]["banners"].append(photo)

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Банер додано ✅")
