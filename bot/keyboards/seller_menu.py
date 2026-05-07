from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


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

def site_menu_kb(subdomain: str, is_active: bool):
    buttons = [

        [InlineKeyboardButton(text="📞 Контакти", callback_data="site:contacts:menu")],
        [InlineKeyboardButton(text="📍 Адреси та карта", callback_data="site:location:menu")],
        [InlineKeyboardButton(text="🎨 Медіа та дизайн", callback_data="site:media:menu")],
    ]

    if is_active:
        buttons.append([
            InlineKeyboardButton(
                text="🌍 Відкрити сайт",
                url=f"https://worker-production-e30f.up.railway.app/site/{subdomain}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
