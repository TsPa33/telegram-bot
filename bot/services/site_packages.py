"""Centralized website package and demo site presentation config."""

from __future__ import annotations

from bot.config import ADMIN_IDS
from bot.database.repositories.crm_admin_repo import list_admin_users
from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.services.domain_service import build_site_url

SITE_PACKAGES = {
    "standard": {
        "title": "Сайт Стандарт",
        "emoji": "🧩",
        "price": 499,
        "description": "Готовий шаблон: послуги, контакти, карта, кнопка дзвінка.",
        "button_text": "💳 Замовити Стандарт",
        "payment_product": "site",
    },
    "plus": {
        "title": "Сайт Візитка Plus",
        "emoji": "🚘",
        "price": 1499,
        "description": "Шаблон + базовий дизайн + банер + наповнення до 5 послуг.",
        "button_text": "💳 Замовити Plus",
    },
    "premium": {
        "title": "Преміум / Індивідуальний",
        "emoji": "🏆",
        "price_from": 3999,
        "description": "Індивідуальний стиль, каталог, банери, тексти, підготовка під рекламу.",
        "button_text": "💳 Індивідуальне замовлення",
    },
}

DEMO_SITE_GROUPS = {
    "premium": {
        "title": "Преміум індивідуальний",
        "emoji": "🏆",
        "description": "Преміум інтернет-магазин автозапчастин з каталогом та CRM заявками.",
        "demos": [
            {
                "subdomain": "demo-parts",
                "title": "Premium Parts Store",
                "button_text": "🏆 Premium Parts Store",
                "description": "Преміум інтернет-магазин автозапчастин з каталогом та CRM заявками.",
            },
        ],
    },
    "business": {
        "title": "Сайт-візитка автопослуг",
        "emoji": "🚘",
        "description": "Преміум сайт-візитка автоелектрика та діагностики.",
        "demos": [
            {
                "subdomain": "demo-electric",
                "title": "Auto Electric Premium",
                "button_text": "🚘 Auto Electric Premium",
                "description": "Преміум сайт-візитка автоелектрика та діагностики.",
            },
        ],
    },
    "standard": {
        "title": "Стандартні шаблони",
        "emoji": "🧩",
        "description": "Швидкий запуск стандартного сайту автопослуг.",
        "demos": [
            {
                "subdomain": "demo-sto",
                "title": "CarPot AutoService",
                "button_text": "🔧 Демо СТО",
                "description": "Готовий сайт СТО з hero-блоком, 8 послугами, контактами, картою та заявками.",
            },
            {
                "subdomain": "demo-tow",
                "title": "CarPot Tow Service",
                "button_text": "🚛 Демо евакуатора",
                "description": "Демо служби евакуатора 24/7 з послугами, месенджерами, картою та callback-формою.",
            },
            {
                "subdomain": "demo-shynomontag",
                "title": "CarPot Tyre Service",
                "button_text": "🛞 Демо шиномонтажу",
                "description": "Повноцінний демо-сайт шиномонтажу із сезонними послугами, контактами і заявкою.",
            },
        ],
    },
}


def get_site_package(package_key: str) -> dict | None:
    return SITE_PACKAGES.get(package_key)


def get_site_package_amount(package_key: str) -> int | None:
    package = get_site_package(package_key)
    if not package:
        return None
    return package.get("price") or package.get("price_from")


def format_site_package_price(package: dict) -> str:
    if package.get("price_from"):
        return f"від {package['price_from']} грн"
    return f"{package['price']} грн"


def format_site_package_title(package_key: str) -> str:
    package = SITE_PACKAGES[package_key]
    return f"{package['title']} — {format_site_package_price(package)}"


def format_site_packages_text() -> str:
    sections = ["💳 <b>Пакети сайтів</b>\n\nОберіть формат:"]

    for package in SITE_PACKAGES.values():
        sections.append(
            f"{package['emoji']} <b>{package['title']}</b> — {format_site_package_price(package)}\n"
            f"{package['description']}"
        )

    return "\n\n".join(sections)


def get_demo_site_url(subdomain: str) -> str:
    return build_site_url(subdomain)


def get_demo_group(group_key: str) -> dict | None:
    return DEMO_SITE_GROUPS.get(group_key)


def get_demo_site(subdomain: str) -> dict | None:
    for group_key, group in DEMO_SITE_GROUPS.items():
        for demo in group["demos"]:
            if demo["subdomain"] == subdomain:
                return {**demo, "category": group_key}
    return None


def known_demo_subdomains() -> set[str]:
    return {
        demo["subdomain"]
        for group in DEMO_SITE_GROUPS.values()
        for demo in group["demos"]
    }


async def notify_admins_about_site_package(bot, user, package_key: str) -> None:
    package = get_site_package(package_key)
    if not package:
        return

    username = f"@{user.username}" if user.username else "—"
    text = (
        "🌐 <b>Нова заявка на сайт</b>\n\n"
        "Пакет:\n"
        f"{package['title']} — {format_site_package_price(package)}\n\n"
        "Користувач:\n"
        f"{username}\n\n"
        "Telegram ID:\n"
        f"{user.id}"
    )

    admin_ids = set(ADMIN_IDS)

    try:
        admin_rows = await list_admin_users()
        admin_ids.update(
            row["telegram_id"]
            for row in admin_rows
            if row.get("is_active") and row.get("role") in {"super_admin", "admin"}
        )
    except Exception as e:
        print("ERROR LOAD ADMINS FOR SITE PACKAGE:", e)

    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            print("ERROR SEND SITE PACKAGE ADMIN NOTIFY:", admin_id, e)


async def get_or_create_package_seller(user):
    from bot.database.repositories.seller_repo import get_or_create_seller

    seller = await get_seller_by_telegram_id(user.id)
    if seller:
        return seller

    return await get_or_create_seller(user.id, user.username)
