import json
import re

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.states.seller_states import SellerSiteStates
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.database.repositories.service_repo import create_service
from bot.services.seller_identity import resolve_seller, resolve_seller_from_user

from bot.keyboards.seller_menu import (
    site_menu_kb,
    contacts_menu_kb,
    location_menu_kb,
    media_menu_kb,
)

router = Router()


# ================= PHONE NORMALIZATION =================

def normalize_phone(phone: str) -> str | None:
    phone = phone.strip().replace(" ", "")

    if phone.startswith("0"):
        phone = "+38" + phone

    if re.fullmatch(r"\+380\d{9}", phone):
        return phone

    return None


# ================= HELPERS =================

async def get_context(callback: CallbackQuery):
    seller = await resolve_seller_from_user(callback.from_user)
    if not seller:
        return None, None

    site = await get_site_by_seller(seller["id"])
    return seller, site


# ================= MENU NAVIGATION =================

@router.callback_query(F.data == "site:contacts:menu")
async def open_contacts(callback: CallbackQuery):
    await callback.message.edit_text("📞 Контакти", reply_markup=contacts_menu_kb())


@router.callback_query(F.data == "site:location:menu")
async def open_location(callback: CallbackQuery):
    await callback.message.edit_text("📍 Адреси та карта", reply_markup=location_menu_kb())


@router.callback_query(F.data == "site:media:menu")
async def open_media(callback: CallbackQuery):
    await callback.message.edit_text("🎨 Медіа та дизайн", reply_markup=media_menu_kb())


@router.callback_query(F.data == "site:back")
async def go_back(callback: CallbackQuery):
    seller = await resolve_seller_from_user(callback.from_user)
    site = await get_site_by_seller(seller["id"])

    await callback.message.edit_text(
        "🌐 Мій сайт",
        reply_markup=site_menu_kb(
            subdomain=site["subdomain"],
            is_active=True
        )
    )


# ================= SERVICES =================

@router.callback_query(F.data == "site:services:add")
async def service_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_service_create)
    await callback.message.answer("Введи назву послуги")
    await callback.answer()


@router.message(SellerSiteStates.site_service_create)
async def service_create_process(message: Message, state: FSMContext):
    seller = await resolve_seller(message)

    await create_service(
        seller_id=seller["id"],
        category="default",
        title=message.text,
        city="",
        address="",
        description=None,
        website=None,
        photo_id=None,
    )

    await state.clear()
    await message.answer("Послугу створено ✅")


# ================= CONTACTS =================

# -------- ADD PHONE --------

@router.callback_query(F.data == "contacts:add_phone")
async def add_phone(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_add_phone)

    await callback.message.answer(
        "📞 Введіть номер телефону\n\n"
        "Формат:\n"
        "+380XXXXXXXXX\n\n"
        "Приклад:\n"
        "+380991234567 або 0991234567"
    )

    await callback.answer()


@router.message(SellerSiteStates.site_contact_add_phone)
async def save_phone(message: Message, state: FSMContext):
    phone = normalize_phone(message.text)

    if not phone:
        await message.answer(
            "❌ Невірний формат номера\n\n"
            "Введіть у форматі:\n"
            "+380XXXXXXXXX\n\n"
            "Приклад:\n"
            "+380991234567 або 0991234567"
        )
        return

    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    config = site.get("config_draft") or {}
    if isinstance(config, str):
        config = json.loads(config)

    phones = config.get("contacts", {}).get("phones", [])
    phones.append(phone)

    await update_site_config(site["id"], {
        "contacts": {
            "phones": phones
        }
    })

    await state.clear()
    await message.answer(f"Номер додано ✅\n{phone}")


# -------- PHONE LIST --------

@router.callback_query(F.data == "contacts:list_phones")
async def list_phones(callback: CallbackQuery):
    seller = await resolve_seller_from_user(callback.from_user)
    site = await get_site_by_seller(seller["id"])

    config = site.get("config_draft") or {}
    if isinstance(config, str):
        config = json.loads(config)

    phones = config.get("contacts", {}).get("phones", [])

    if not phones:
        await callback.message.answer("Список номерів порожній")
        await callback.answer()
        return

    for i, phone in enumerate(phones):
        await callback.message.answer(
            f"{i + 1}. {phone}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="❌ Видалити",
                        callback_data=f"contacts:delete_phone:{i}"
                    )
                ]]
            )
        )

    await callback.answer()


# -------- DELETE PHONE --------

@router.callback_query(F.data.startswith("contacts:delete_phone:"))
async def delete_phone(callback: CallbackQuery):
    index = int(callback.data.split(":")[-1])

    seller = await resolve_seller_from_user(callback.from_user)
    site = await get_site_by_seller(seller["id"])

    config = site.get("config_draft") or {}
    if isinstance(config, str):
        config = json.loads(config)

    phones = config.get("contacts", {}).get("phones", [])

    if index >= len(phones):
        await callback.answer("Помилка", show_alert=True)
        return

    deleted = phones.pop(index)

    await update_site_config(site["id"], {
        "contacts": {
            "phones": phones
        }
    })

    await callback.answer("Номер видалено")
    await callback.message.answer(f"Видалено: {deleted}")


# -------- TELEGRAM --------

@router.callback_query(F.data == "contacts:telegram")
async def set_tg(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_telegram)
    await callback.message.answer("Введи username (без @)")
    await callback.answer()


@router.message(SellerSiteStates.site_contact_telegram)
async def save_tg(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "messengers": {
                "telegram": message.text
            }
        }
    })

    await state.clear()
    await message.answer("Telegram збережено ✅")


# -------- WHATSAPP --------

@router.callback_query(F.data == "contacts:whatsapp")
async def set_wa(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_whatsapp)
    await callback.message.answer("Введи номер WhatsApp")
    await callback.answer()


@router.message(SellerSiteStates.site_contact_whatsapp)
async def save_wa(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "messengers": {
                "whatsapp": message.text
            }
        }
    })

    await state.clear()
    await message.answer("WhatsApp збережено ✅")


# -------- VIBER --------

@router.callback_query(F.data == "contacts:viber")
async def set_viber(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_viber)
    await callback.message.answer("Введи номер Viber")
    await callback.answer()


@router.message(SellerSiteStates.site_contact_viber)
async def save_viber(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "messengers": {
                "viber": message.text
            }
        }
    })

    await state.clear()
    await message.answer("Viber збережено ✅")


# -------- INSTAGRAM --------

@router.callback_query(F.data == "contacts:instagram")
async def set_inst(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_instagram)
    await callback.message.answer("Встав посилання Instagram")
    await callback.answer()


@router.message(SellerSiteStates.site_contact_instagram)
async def save_inst(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "socials": {
                "instagram": message.text
            }
        }
    })

    await state.clear()
    await message.answer("Instagram збережено ✅")


# -------- FACEBOOK --------

@router.callback_query(F.data == "contacts:facebook")
async def set_fb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_facebook)
    await callback.message.answer("Встав посилання Facebook")
    await callback.answer()


@router.message(SellerSiteStates.site_contact_facebook)
async def save_fb(message: Message, state: FSMContext):
    seller = await resolve_seller(message)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "socials": {
                "facebook": message.text
            }
        }
    })

    await state.clear()
    await message.answer("Facebook збережено ✅")
