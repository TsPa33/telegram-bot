import json
import re

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.states.seller_states import SellerSiteStates
from bot.database.repositories.site_repo import (
    get_site_by_seller,
    subdomain_exists,
    update_site_config,
    update_site_subdomain,
)
from bot.database.repositories.service_repo import create_service
from bot.services.demo_context import clear_preserving_demo_context, resolve_active_seller, resolve_active_seller_from_user, is_demo_mode

from bot.keyboards.seller_menu import (
    site_menu_kb,
    site_menu_text,
    contacts_menu_kb,
    location_menu_kb,
    media_menu_kb,
    theme_menu_kb,
    site_domain_input_kb,
    site_domain_kb,
    site_domain_success_kb,
    texts_menu_kb,
    stats_menu_kb,
)
from bot.services.domain_service import build_site_url, normalize_subdomain, validate_subdomain

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

async def get_context(callback: CallbackQuery, state: FSMContext):
    seller = await resolve_active_seller_from_user(callback.from_user, state)

    if not seller:
        return None, None

    site = await get_site_by_seller(seller["id"])

    return seller, site


def safe_config(raw):
    if not raw:
        return {}

    if isinstance(raw, str):
        try:
            config = json.loads(raw)
        except Exception:
            return {}
    else:
        config = dict(raw)

    contacts = config.get("contacts", {})

    if isinstance(contacts, dict):
        old_phone = contacts.pop("phone", None)

        if old_phone:
            contacts.setdefault("phones", [])

            if old_phone not in contacts["phones"]:
                contacts["phones"].append(old_phone)

        old_telegram = contacts.pop("telegram", None)

        if old_telegram:
            contacts.setdefault("messengers", {})
            contacts["messengers"]["telegram"] = old_telegram

        contacts.setdefault("phones", [])
        contacts.setdefault("messengers", {})
        contacts.setdefault("socials", {})

        contacts["messengers"].setdefault("telegram", "")
        contacts["messengers"].setdefault("whatsapp", "")
        contacts["messengers"].setdefault("viber", "")

        contacts["socials"].setdefault("instagram", "")
        contacts["socials"].setdefault("facebook", "")

        config["contacts"] = contacts

    return config


# ================= MENU NAVIGATION =================

DOMAIN_SETTINGS_TEXT = (
    "🌐 Налаштування домену\n\n"
    "Ваш сайт буде доступний за адресою:\n\n"
    "https://ваш-домен.carpot.com.ua\n\n"
    "Приклад:\n"
    "razborka-kyiv.carpot.com.ua\n\n"
    "Дозволено:\n"
    "• латинські букви\n"
    "• цифри\n"
    "• дефіс -\n\n"
    "Приклад домену:\n"
    "razborka\n"
    "sto-lviv\n"
    "evakuator-kyiv\n\n"
    "Введіть бажаний домен:"
)

INVALID_DOMAIN_TEXT = (
    "❌ Некоректний домен.\n\n"
    "Дозволено:\n"
    "• латинські букви\n"
    "• цифри\n"
    "• дефіс -\n\n"
    "Приклад:\n"
    "sto-lviv"
)


async def send_domain_settings_message(callback: CallbackQuery, state: FSMContext):
    seller, site = await get_context(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    subdomain = normalize_subdomain(site.get("subdomain"))
    text = DOMAIN_SETTINGS_TEXT

    if subdomain:
        text = (
            "🌐 Налаштування домену\n\n"
            "Поточний домен:\n"
            f"{build_site_url(subdomain)}\n\n"
            "Ви можете змінити домен сайту.\n\n"
            + DOMAIN_SETTINGS_TEXT.split("\n\n", 1)[1]
        )

    await callback.message.edit_text(
        text,
        reply_markup=site_domain_kb(subdomain),
    )
    await callback.answer()


@router.callback_query(F.data == "site:domain:menu")
async def open_domain_menu(callback: CallbackQuery, state: FSMContext):
    await send_domain_settings_message(callback, state)


@router.callback_query(F.data == "site:view")
async def view_site_without_domain(callback: CallbackQuery, state: FSMContext):
    seller, site = await get_context(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site or not normalize_subdomain(site.get("subdomain")):
        await callback.answer("Спочатку створіть домен сайту.", show_alert=True)
        return

    await callback.answer("Відкрийте сайт кнопкою перегляду в меню.", show_alert=True)


@router.callback_query(F.data == "site:domain:change")
async def start_domain_change(callback: CallbackQuery, state: FSMContext):
    seller, site = await get_context(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    await state.set_state(SellerSiteStates.site_subdomain)
    await callback.message.edit_text(
        DOMAIN_SETTINGS_TEXT,
        reply_markup=site_domain_input_kb(),
    )
    await callback.answer()


@router.message(SellerSiteStates.site_subdomain)
async def save_site_subdomain(message: Message, state: FSMContext):
    seller = await resolve_active_seller(message, state)

    if not seller:
        await message.answer("Продавця не знайдено")
        return

    desired_subdomain = normalize_subdomain(message.text)

    if not validate_subdomain(message.text):
        await message.answer(INVALID_DOMAIN_TEXT, reply_markup=site_domain_input_kb())
        return

    if await subdomain_exists(desired_subdomain, exclude_seller_id=seller["id"]):
        await message.answer(
            "❌ Домен вже зайнятий.\n\n"
            "Спробуйте:\n"
            f"{desired_subdomain}-ua\n"
            f"{desired_subdomain}-kyiv\n"
            f"{desired_subdomain}-service",
            reply_markup=site_domain_input_kb(),
        )
        return

    site = await update_site_subdomain(seller["id"], desired_subdomain)

    if not site:
        await message.answer(
            "❌ Домен вже зайнятий.\n\n"
            "Спробуйте:\n"
            f"{desired_subdomain}-ua\n"
            f"{desired_subdomain}-kyiv\n"
            f"{desired_subdomain}-service",
            reply_markup=site_domain_input_kb(),
        )
        return

    await clear_preserving_demo_context(state)
    await state.update_data(flow="seller_site")

    await message.answer(
        "✅ Домен успішно оновлено\n\n"
        "Ваш сайт:\n"
        f"{build_site_url(desired_subdomain)}",
        reply_markup=site_domain_success_kb(desired_subdomain),
    )


@router.callback_query(F.data == "site:contacts:menu")
async def open_contacts(callback: CallbackQuery):
    await callback.message.edit_text(
        "📞 Контакти",
        reply_markup=contacts_menu_kb()
    )

    await callback.answer()


@router.callback_query(F.data == "site:location:menu")
async def open_location(callback: CallbackQuery):
    await callback.message.edit_text(
        "📍 Адреси та карта",
        reply_markup=location_menu_kb()
    )

    await callback.answer()


@router.callback_query(F.data == "site:media:menu")
async def open_media(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎨 Медіа та дизайн",
        reply_markup=media_menu_kb()
    )

    await callback.answer()


@router.callback_query(F.data == "site:texts:menu")
async def open_texts(callback: CallbackQuery):
    await callback.message.edit_text(
        "✏️ Тексти сайту\n\n"
        "Тут можна змінити основні тексти сайту. "
        "Додаткові текстові блоки будуть доступні пізніше.",
        reply_markup=texts_menu_kb(),
    )

    await callback.answer()


@router.callback_query(F.data == "site:stats:menu")
async def open_site_stats(callback: CallbackQuery):
    await callback.message.edit_text(
        "📊 Статистика сайту\n\n"
        "Статистика сайту буде доступна після перших переглядів та заявок.",
        reply_markup=stats_menu_kb(),
    )

    await callback.answer()


@router.callback_query(F.data == "site:theme:menu")
async def open_theme_menu(callback: CallbackQuery, state: FSMContext):
    seller, site = await get_context(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = safe_config(site.get("config_draft"))
    current_scheme = (config.get("theme") or {}).get("scheme") or "default"

    await callback.message.edit_text(
        "🎨 Кольорова схема",
        reply_markup=theme_menu_kb(current_scheme)
    )

    await callback.answer()


@router.callback_query(F.data.startswith("site:theme:set:"))
async def set_theme_scheme(callback: CallbackQuery, state: FSMContext):
    allowed_schemes = {"default", "light_blue", "neon_dark", "premium_dark"}
    scheme = callback.data.split(":")[-1]

    if scheme not in allowed_schemes:
        await callback.answer("Невідома кольорова схема", show_alert=True)
        return

    seller, site = await get_context(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    await update_site_config(site["id"], {
        "theme": {
            "scheme": scheme,
        }
    })

    await callback.message.edit_text(
        "🎨 Кольорова схема",
        reply_markup=theme_menu_kb(scheme)
    )

    await callback.answer("✅ Кольорову схему збережено")


@router.callback_query(F.data == "site:back")
async def go_back(callback: CallbackQuery, state: FSMContext):
    seller = await resolve_active_seller_from_user(callback.from_user, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    site = await get_site_by_seller(seller["id"])

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    status = site.get("status", "active")
    is_active = status == "active"

    await callback.message.edit_text(
        site_menu_text(subdomain=site["subdomain"], status=status, is_active=is_active),
        reply_markup=site_menu_kb(
            subdomain=site["subdomain"],
            is_active=is_active,
            demo_mode=await is_demo_mode(state)
        )
    )

    await callback.answer()


# ================= LOCATION =================

@router.callback_query(F.data == "site:contacts:address")
async def edit_address(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_address)

    await callback.message.answer(
        "📍 Введіть адресу\n\n"
        "Приклад:\n"
        "м. Київ, вул. Центральна, 10"
    )

    await callback.answer()


@router.message(SellerSiteStates.site_contact_address)
async def save_address(message: Message, state: FSMContext):
    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await clear_preserving_demo_context(state)
        await message.answer("❌ Сайт не знайдено")
        return

    address = message.text.strip()

    if not address:
        await message.answer("❌ Адреса не може бути порожньою")
        return

    config = safe_config(site.get("config_draft"))

    contacts = config.get("contacts", {})
    contacts["address"] = address

    map_config = config.get("map", {})
    map_config["address"] = address

    await update_site_config(site["id"], {
        "contacts": contacts,
        "map": map_config,
    })

    await clear_preserving_demo_context(state)

    await message.answer(
        "✅ Адресу збережено\n\n"
        f"📍 {address}"
    )


@router.callback_query(F.data == "site:contacts:map")
async def edit_map(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_map)

    await callback.message.answer(
        "🗺 Вставте HTML iframe Google Maps\n\n"
        "Приклад:\n"
        "<iframe src='...'></iframe>"
    )

    await callback.answer()


@router.message(SellerSiteStates.site_contact_map)
async def save_map(message: Message, state: FSMContext):
    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    if not site:
        await clear_preserving_demo_context(state)
        await message.answer("❌ Сайт не знайдено")
        return

    map_embed = message.text.strip()

    if "<iframe" not in map_embed or "</iframe>" not in map_embed:
        await message.answer(
            "❌ Невірний формат карти\n\n"
            "Потрібно вставити iframe код Google Maps."
        )
        return

    config = safe_config(site.get("config_draft"))

    contacts = config.get("contacts", {})
    contacts["map_embed"] = map_embed

    await update_site_config(site["id"], {
        "contacts": contacts
    })

    await clear_preserving_demo_context(state)

    await message.answer("✅ Карту збережено")


# ================= SERVICES =================

@router.callback_query(F.data == "site:services:add")
async def service_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_service_create)
    await callback.message.answer("Введи назву послуги")
    await callback.answer()


@router.message(SellerSiteStates.site_service_create)
async def service_create_process(message: Message, state: FSMContext):
    seller = await resolve_active_seller(message, state)

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

    await clear_preserving_demo_context(state)

    await message.answer("Послугу створено ✅")


# ================= CONTACTS =================

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

    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    config = safe_config(site.get("config_draft"))
    phones = config.get("contacts", {}).get("phones", [])

    if phone not in phones:
        phones.append(phone)

    await update_site_config(site["id"], {
        "contacts": {
            "phones": phones
        }
    })

    await clear_preserving_demo_context(state)

    await message.answer(f"Номер додано ✅\n{phone}")


@router.callback_query(F.data == "contacts:list_phones")
async def list_phones(callback: CallbackQuery, state: FSMContext):
    seller = await resolve_active_seller_from_user(callback.from_user, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    site = await get_site_by_seller(seller["id"])

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = safe_config(site.get("config_draft"))
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


@router.callback_query(F.data.startswith("contacts:delete_phone:"))
async def delete_phone(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.split(":")[-1])

    seller = await resolve_active_seller_from_user(callback.from_user, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    site = await get_site_by_seller(seller["id"])

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = safe_config(site.get("config_draft"))
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


@router.callback_query(F.data == "contacts:telegram")
async def set_tg(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_telegram)

    await callback.message.answer(
        "💬 Введіть Telegram username\n\n"
        "Формат:\n"
        "username або @username\n\n"
        "Приклад:\n"
        "@carpot_support"
    )

    await callback.answer()


@router.message(SellerSiteStates.site_contact_telegram)
async def save_tg(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")

    if not username:
        await message.answer("❌ Username не може бути порожнім")
        return

    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "messengers": {
                "telegram": username
            }
        }
    })

    await clear_preserving_demo_context(state)

    await message.answer(f"Telegram збережено ✅\n@{username}")


@router.callback_query(F.data == "contacts:whatsapp")
async def set_wa(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_whatsapp)

    await callback.message.answer(
        "📞 Введіть номер WhatsApp\n\n"
        "Формат:\n"
        "+380XXXXXXXXX\n\n"
        "Приклад:\n"
        "+380991234567 або 0991234567"
    )

    await callback.answer()


@router.message(SellerSiteStates.site_contact_whatsapp)
async def save_wa(message: Message, state: FSMContext):
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

    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "messengers": {
                "whatsapp": phone
            }
        }
    })

    await clear_preserving_demo_context(state)

    await message.answer(f"WhatsApp збережено ✅\n{phone}")


@router.callback_query(F.data == "contacts:viber")
async def set_viber(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_viber)

    await callback.message.answer(
        "📞 Введіть номер Viber\n\n"
        "Формат:\n"
        "+380XXXXXXXXX\n\n"
        "Приклад:\n"
        "+380991234567 або 0991234567"
    )

    await callback.answer()


@router.message(SellerSiteStates.site_contact_viber)
async def save_viber(message: Message, state: FSMContext):
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

    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "messengers": {
                "viber": phone
            }
        }
    })

    await clear_preserving_demo_context(state)

    await message.answer(f"Viber збережено ✅\n{phone}")


@router.callback_query(F.data == "contacts:instagram")
async def set_inst(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_instagram)

    await callback.message.answer(
        "📷 Вставте посилання Instagram\n\n"
        "Приклад:\n"
        "https://instagram.com/your_page"
    )

    await callback.answer()


@router.message(SellerSiteStates.site_contact_instagram)
async def save_inst(message: Message, state: FSMContext):
    url = message.text.strip()

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "socials": {
                "instagram": url
            }
        }
    })

    await clear_preserving_demo_context(state)

    await message.answer(f"Instagram збережено ✅\n{url}")


@router.callback_query(F.data == "contacts:facebook")
async def set_fb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_facebook)

    await callback.message.answer(
        "📘 Вставте посилання Facebook\n\n"
        "Приклад:\n"
        "https://facebook.com/your_page"
    )

    await callback.answer()


@router.message(SellerSiteStates.site_contact_facebook)
async def save_fb(message: Message, state: FSMContext):
    url = message.text.strip()

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    seller = await resolve_active_seller(message, state)
    site = await get_site_by_seller(seller["id"])

    await update_site_config(site["id"], {
        "contacts": {
            "socials": {
                "facebook": url
            }
        }
    })

    await clear_preserving_demo_context(state)

    await message.answer(f"Facebook збережено ✅\n{url}")


# ================= BANNERS =================

@router.callback_query(F.data == "media:add_banner")
@router.callback_query(F.data == "site:edit:banners")
async def add_banner(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_banner)
    await callback.message.answer("Надішліть зображення банера")
    await callback.answer()


@router.callback_query(F.data == "media:list_banners")
@router.callback_query(F.data == "site:banners:list")
async def list_banners(callback: CallbackQuery, state: FSMContext):
    seller = await resolve_active_seller_from_user(callback.from_user, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    site = await get_site_by_seller(seller["id"])

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = safe_config(site.get("config_draft"))
    banners = config.get("hero", {}).get("banners", [])

    if not banners:
        await callback.message.answer("Банери відсутні")
        await callback.answer()
        return

    for i, banner in enumerate(banners):
        await callback.message.answer(
            f"{i + 1}. {banner}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="❌ Видалити",
                        callback_data=f"site:banners:delete:{i}"
                    )
                ]]
            )
        )

    await callback.answer()


@router.callback_query(F.data.startswith("media:delete_banner:"))
@router.callback_query(F.data.startswith("site:banners:delete:"))
async def delete_banner(callback: CallbackQuery, state: FSMContext):
    index = int(callback.data.split(":")[-1])

    seller = await resolve_active_seller_from_user(callback.from_user, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    site = await get_site_by_seller(seller["id"])

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    config = safe_config(site.get("config_draft"))
    hero = config.get("hero", {})
    banners = hero.get("banners", [])

    if index >= len(banners):
        await callback.answer("Помилка", show_alert=True)
        return

    deleted = banners.pop(index)
    hero["banners"] = banners

    await update_site_config(site["id"], {
        "hero": hero
    })

    await callback.answer("Видалено")

    await callback.message.answer(
        f"Банер видалено:\n{deleted}"
    )
