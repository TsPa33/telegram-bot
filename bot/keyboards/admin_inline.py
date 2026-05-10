from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ================= EXISTING =================

def brand_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"admin:brand:ok:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Reject",
                callback_data=f"admin:brand:no:{request_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Edit",
                callback_data=f"admin:brand:edit:{request_id}"
            )
        ]
    ])


def model_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"admin:model:ok:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Reject",
                callback_data=f"admin:model:no:{request_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Edit",
                callback_data=f"admin:model:edit:{request_id}"
            )
        ]
    ])


def verification_request_kb(request_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Approve",
                callback_data=f"admin:verify:ok:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Reject",
                callback_data=f"admin:verify:no:{request_id}"
            )
        ]
    ])


# ================= NEW: USERS =================

def admin_users_kb(users):
    """
    Список користувачів
    """
    buttons = []

    for u in users:
        label = f"{u['id']} | {u.get('username') or 'no_name'}"

        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"admin:user:{u['id']}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_user_actions_kb(user_id: int):
    """
    Дії над користувачем
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="👁 Переглянути",
                callback_data=f"admin:view:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Видалити",
                callback_data=f"admin:delete:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅ Назад",
                callback_data="admin:users"
            )
        ]
    ])


def admin_confirm_delete_kb(user_id: int):
    """
    Підтвердження видалення
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚠️ Підтвердити видалення",
                callback_data=f"admin:delete_confirm:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Скасувати",
                callback_data=f"admin:user:{user_id}"
            )
        ]
    ])


# ================= DEMO SITES =================

def admin_demo_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати демо сайт", callback_data="admin:demo:add")],
        [InlineKeyboardButton(text="📋 Список демо сайтів", callback_data="admin:demo:list")],
    ])


def admin_demo_sites_kb(sites):
    buttons = []

    for site in sites:
        config = site.get("config_draft") or {}
        title = (config.get("header") or {}).get("title") if isinstance(config, dict) else None
        title = title or site.get("seller_shop_name") or site.get("seller_name") or site["subdomain"]

        buttons.append([
            InlineKeyboardButton(
                text=f"{title} — {site['subdomain']}",
                callback_data=f"admin:demo:view:{site['id']}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="admin:demo:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_demo_site_actions_kb(site):
    subdomain = site["subdomain"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"admin:demo:edit:{site['id']}")],
        [InlineKeyboardButton(
            text="🌐 Відкрити сайт",
            url=f"https://worker-production-e30f.up.railway.app/site/{subdomain}"
        )],
        [InlineKeyboardButton(text="🌱 Заповнити demo контентом", callback_data=f"admin:demo:seed:{site['id']}")],
        [InlineKeyboardButton(text="🗑 Видалити", callback_data=f"admin:demo:delete:{site['id']}")],
        [InlineKeyboardButton(text="⬅ До списку", callback_data="admin:demo:list")],
    ])


def admin_demo_confirm_delete_kb(site_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Так, видалити", callback_data=f"admin:demo:delete_confirm:{site_id}")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"admin:demo:view:{site_id}")],
    ])


def admin_demo_seed_types_kb(site_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛞 Шиномонтаж", callback_data=f"admin:demo:seed_type:{site_id}:tire")],
        [InlineKeyboardButton(text="🛠 СТО", callback_data=f"admin:demo:seed_type:{site_id}:sto")],
        [InlineKeyboardButton(text="🚛 Евакуатор", callback_data=f"admin:demo:seed_type:{site_id}:tow")],
        [InlineKeyboardButton(text="⚡ Автоелектрик", callback_data=f"admin:demo:seed_type:{site_id}:electric")],
        [InlineKeyboardButton(text="🚗 Автозапчастини", callback_data=f"admin:demo:seed_type:{site_id}:parts")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data=f"admin:demo:view:{site_id}")],
    ])
