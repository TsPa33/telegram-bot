from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


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
            KeyboardButton(text="🌐 Мій сайт"),
        ],
        [
            KeyboardButton(text="💳 Пакети послуг"),
            KeyboardButton(text="↩️ На головне меню"),
        ],
    ])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )


def seller_menu_kb(is_verified: bool = False):
    return seller_main_kb(is_verified=is_verified)


# 🔥 CMS MENU (FINAL)
def site_menu_kb(subdomain: str, is_active: bool) -> InlineKeyboardMarkup:
    buttons = [
        # HEADER
        [InlineKeyboardButton(text="✏️ Шапка", callback_data="site:edit:header")],

        # SERVICES
        [InlineKeyboardButton(text="🛠 Послуги", callback_data="site:services:menu")],
        [InlineKeyboardButton(text="➕ Додати послугу", callback_data="site:services:add")],
        [InlineKeyboardButton(text="📋 Список послуг", callback_data="site:services:list")],
        [InlineKeyboardButton(text="🔛 Вкл/Викл", callback_data="module:toggle:services")],

        # CARS
        [InlineKeyboardButton(text="🚗 Авто", callback_data="site:cars:menu")],
        [InlineKeyboardButton(text="➕ Додати авто", callback_data="site:cars:add")],
        [InlineKeyboardButton(text="📋 Список авто", callback_data="site:cars:list")],
        [InlineKeyboardButton(text="❌ Видалити авто", callback_data="site:cars:delete")],

        # CONTACTS
        [InlineKeyboardButton(text="📞 Контакти", callback_data="site:contacts:menu")],
        [InlineKeyboardButton(text="✏️ Телефон", callback_data="site:contacts:phone")],
        [InlineKeyboardButton(text="✏️ Адреса", callback_data="site:contacts:address")],
        [InlineKeyboardButton(text="✏️ Карта", callback_data="site:contacts:map")],

        # MEDIA
        [InlineKeyboardButton(text="🖼 Банери", callback_data="site:edit:banners")],
        [InlineKeyboardButton(text="🖼 Лого", callback_data="site:edit:logo")],
    ]

    if is_active:
        buttons.append([
            InlineKeyboardButton(
                text="🌍 Відкрити сайт",
                url=f"https://worker-production-e30f.up.railway.app/site/{subdomain}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)