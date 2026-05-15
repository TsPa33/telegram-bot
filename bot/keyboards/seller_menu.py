from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from bot.services.domain_service import build_site_url, normalize_subdomain


# ================= MAIN =================

def seller_main_kb(is_verified: bool = False):
    buttons = []

    if not is_verified:
        buttons.append([
            KeyboardButton(text="🔐 Верифікація")
        ])

    buttons.extend([
        [
            KeyboardButton(text="➕ Додати авто"),
            KeyboardButton(text="➕ Додати послугу"),
        ],
        [
            KeyboardButton(text="📋 Мій гараж"),
            KeyboardButton(text="📋 Мої послуги"),
        ],
        [
            KeyboardButton(text="👤 Мій профіль"),
            KeyboardButton(text="📊 Статистика"),
        ],
        [
            KeyboardButton(text="💳 Пакети послуг"), 
            KeyboardButton(text="🌐 Мій сайт"),
        ],
        [
            KeyboardButton(text="💼 Професійна CRM"),
        ],
        [
            KeyboardButton(text="💬 Підтримка"),
        ],
        [
            KeyboardButton(text="↩️ На головне меню"),  # ✅ ДОДАНО
        ],
    ])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )


def seller_menu_kb(is_verified: bool = False):
    return seller_main_kb(is_verified=is_verified)


# ================= SITE MAIN =================

def site_status_label(status: str | None = None, is_active: bool | None = None) -> str:
    normalized_status = (status or "").strip().lower()

    if is_active is True or normalized_status in {"active", "published", "опубліковано"}:
        return "Опубліковано"

    return "Чернетка"


def site_menu_text(subdomain: str | None, status: str | None = None, is_active: bool | None = None) -> str:
    normalized_subdomain = normalize_subdomain(subdomain)
    site_url = build_site_url(normalized_subdomain) if normalized_subdomain else "—"
    current_domain = normalized_subdomain or "не створено"

    return (
        "🌐 Мій сайт\n\n"
        f"Статус: {site_status_label(status, is_active)}\n"
        f"Поточний домен: {current_domain}\n"
        f"Site URL: {site_url}"
    )


def site_menu_kb(subdomain: str | None, is_active: bool, demo_mode: bool = False):
    normalized_subdomain = normalize_subdomain(subdomain)

    view_button = InlineKeyboardButton(
        text="👁 Переглянути сайт",
        url=build_site_url(normalized_subdomain),
    ) if normalized_subdomain else InlineKeyboardButton(
        text="👁 Переглянути сайт",
        callback_data="site:view",
    )

    buttons = [
        [
            InlineKeyboardButton(text="🌐 Домен сайту", callback_data="site:domain:menu"),
            view_button,
        ],
        [InlineKeyboardButton(text="🚀 Опублікувати сайт", callback_data="site:publish")],
        [
            InlineKeyboardButton(text="🧩 Модулі сайту", callback_data="site:modules:menu"),
            InlineKeyboardButton(text="✏️ Тексти сайту", callback_data="site:texts:menu"),
        ],
        [
            InlineKeyboardButton(text="📞 Контакти", callback_data="site:contacts:menu"),
            InlineKeyboardButton(text="📍 Адреси та карта", callback_data="site:location:menu"),
        ],
        [InlineKeyboardButton(text="🎨 Медіа та дизайн", callback_data="site:media:menu")],
        [InlineKeyboardButton(text="📊 Статистика сайту", callback_data="site:stats:menu")],
    ]

    if demo_mode:
        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Вийти з demo режиму",
                callback_data="demo:exit"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def modules_menu_kb(modules: dict | None = None):
    modules = modules or {}
    module_titles = (
        ("services", "🛠 Послуги"),
        ("cars", "🚗 Авто"),
        ("products", "🧰 Запчастини"),
        ("pricing", "💳 Ціни"),
        ("works", "🧑‍🔧 Роботи"),
        ("gallery", "🖼 Галерея"),
        ("cta", "🚀 CTA"),
        ("reviews", "⭐ Відгуки"),
        ("contacts", "📞 Контакти"),
        ("map", "📍 Карта"),
    )

    buttons = []

    for key, title in module_titles:
        enabled = bool(modules.get(key, True))
        marker = "✅" if enabled else "⬜️"
        buttons.append([
            InlineKeyboardButton(
                text=f"{marker} {title}",
                callback_data=f"module:toggle:{key}",
            )
        ])

    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def texts_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷 Заголовок сайту", callback_data="site:edit:header")],
        [InlineKeyboardButton(text="ℹ️ Блок 'Про нас'", callback_data="site:toggle:about")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")],
    ])


def stats_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")],
    ])


def site_domain_kb(subdomain: str | None = None):
    action_text = "✏️ Змінити домен" if subdomain else "Створити домен"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=action_text, callback_data="site:domain:change")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")],
    ])


def site_domain_success_kb(subdomain: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Відкрити сайт", url=build_site_url(subdomain))],
        [InlineKeyboardButton(text="✏️ Змінити домен", callback_data="site:domain:change")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")],
    ])


def site_domain_input_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")],
    ])


# ================= CONTACTS MENU =================

def contacts_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="➕ Додати номер", callback_data="contacts:add_phone")],
        [InlineKeyboardButton(text="📋 Список номерів", callback_data="contacts:list_phones")],

        [InlineKeyboardButton(text="💬 Telegram", callback_data="contacts:telegram")],
        [InlineKeyboardButton(text="💬 WhatsApp", callback_data="contacts:whatsapp")],
        [InlineKeyboardButton(text="💬 Viber", callback_data="contacts:viber")],

        [InlineKeyboardButton(text="📷 Instagram", callback_data="contacts:instagram")],
        [InlineKeyboardButton(text="📘 Facebook", callback_data="contacts:facebook")],

        [InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")],
    ])


# ================= LOCATION MENU =================

def location_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="📍 Додати / змінити адресу", callback_data="site:contacts:address")],
        [InlineKeyboardButton(text="🗺 Додати / змінити карту", callback_data="site:contacts:map")],

        [InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")],
    ])


# ================= MEDIA MENU =================

def media_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[

        [InlineKeyboardButton(text="🖼 Додати банер", callback_data="site:edit:banners")],
        [InlineKeyboardButton(text="📋 Список банерів", callback_data="site:banners:list")],
        [InlineKeyboardButton(text="🖼 Лого", callback_data="site:edit:logo")],
        [InlineKeyboardButton(text="🖼 Фото товарів", callback_data="site:products:media:list")],
        [InlineKeyboardButton(text="🛠 Фото послуг", callback_data="site:services:media:list")],
        [InlineKeyboardButton(text="🎨 Кольорова схема", callback_data="site:theme:menu")],

        [InlineKeyboardButton(text="⬅ Назад", callback_data="site:back")],
    ])

# ================= THEME MENU =================

def theme_menu_kb(current_scheme: str | None = None):
    current_scheme = current_scheme or "default"

    schemes = (
        ("default", "Стандартна"),
        ("light_blue", "Блакитна"),
        ("neon_dark", "Неонова темна"),
        ("premium_dark", "Преміум темна"),
    )

    buttons = []

    for scheme, title in schemes:
        text = f"✅ {title}" if scheme == current_scheme else title
        buttons.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"site:theme:set:{scheme}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="site:media:menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
