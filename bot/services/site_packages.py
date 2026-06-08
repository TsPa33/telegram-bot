"""Centralized website package and demo site presentation config."""

from __future__ import annotations

from bot.config import ADMIN_IDS
from bot.database.repositories.crm_admin_repo import list_admin_users
from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.services.domain_service import build_site_url

SITE_PACKAGES = {
    "standard": {
        "title": "Сайт для авторозборки",
        "price": 499,
        "price_period": "рік",
        "description": "Власний сайт для авторозборки з каталогом запчастин, VIN-заявками, CRM та Telegram-сповіщеннями. Заявки приходять і з CarPot, і напряму з вашого сайту.",
        "button_text": "Створити сайт",
        "payment_product": "site",
    },
    "plus": {
        "title": "Сайт-візитка для послуг",
        "price": 1499,
        "description": "Сайт для СТО, евакуатора, автоелектрика, шиномонтажу чи іншого автофахівця: послуги, контакти, карта, форми заявок і CRM.",
        "button_text": "Створити сайт-візитку",
    },
    "premium": {
        "title": "Індивідуальний сайт",
        "price_from": 4999,
        "description": "Індивідуальний дизайн, унікальна структура, додаткові модулі, CRM інтеграція, Telegram повідомлення, підготовка під рекламу та SEO налаштування.",
        "button_text": "Обговорити проект",
    },
}

DEMO_SITE_GROUPS = {
    "parts_store": {
        "title": "Інтернет-магазин запчастин",
        "emoji": "🌐",
        "description": "Готове рішення для каталогу запчастин, заявок і CRM-обробки в Telegram.",
        "demos": [
            {
                "subdomain": "demo-parts",
                "title": "Інтернет-магазин запчастин",
                "button_text": "Інтернет-магазин запчастин",
                "description": "Каталог, картки товарів, заявки із сайту прямо в Telegram та CRM.",
            },
        ],
    },
    "service_business": {
        "title": "Сайт-візитка автосервісу",
        "emoji": "🌐",
        "description": "Рішення для презентації послуг, контактів, форм заявок і комунікації з клієнтами.",
        "demos": [
            {
                "subdomain": "demo-electric",
                "title": "Автоелектрик",
                "button_text": "Автоелектрик",
                "description": "Послуги автоелектрика, заявки, Telegram-зв'язок і CRM для роботи з клієнтами.",
            },
        ],
    },
    "autoservice": {
        "title": "СТО",
        "emoji": "🌐",
        "description": "Сайт для СТО з переліком послуг, формами заявок, контактами та інтеграцією з CRM.",
        "demos": [
            {
                "subdomain": "demo-sto",
                "title": "СТО",
                "button_text": "СТО",
                "description": "Готовий сайт СТО з послугами, формами заявок і заявками в Telegram.",
            },
            {
                "subdomain": "demo-tow",
                "title": "Евакуатор",
                "button_text": "Евакуатор",
                "description": "Рішення для служби евакуатора з швидким зверненням клієнта і CRM-обробкою.",
            },
            {
                "subdomain": "demo-shynomontag",
                "title": "Шиномонтаж",
                "button_text": "Шиномонтаж",
                "description": "Сайт шиномонтажу з сезонними послугами, акціями та заявками в Telegram.",
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
    period = package.get("price_period")
    if period:
        return f"{package['price']} грн / {period}"
    return f"{package['price']} грн"


def format_site_package_title(package_key: str) -> str:
    package = SITE_PACKAGES[package_key]
    return f"{package['title']} — {format_site_package_price(package)}"


def format_site_packages_text() -> str:
    sections = [
        "<b>🌐 Власний сайт CarPot</b>",
        "",
        "Сайт — це додатковий канал заявок поруч із маркетплейсом CarPot.",
        "Клієнт може знайти вас у CarPot або напряму через ваш сайт.",
        "",
        "<b>Сайт для авторозборки — 499 грн / рік</b>",
        "✓ Власний сайт",
        "✓ Каталог запчастин",
        "✓ VIN заявки",
        "✓ CRM",
        "✓ Telegram сповіщення",
        "✓ Заявки з CarPot",
        "✓ Заявки з власного сайту",
        "👉 Створити сайт",
        "",
        "<b>Сайт-візитка для послуг — 1499 грн</b>",
        "✓ СТО",
        "✓ Евакуатор",
        "✓ Автоелектрик",
        "✓ Шиномонтаж",
        "✓ Контакти",
        "✓ Карта",
        "✓ CRM",
        "👉 Створити сайт-візитку",
        "",
        "<b>Індивідуальний сайт — від 4999 грн</b>",
        "✓ Індивідуальний дизайн",
        "✓ Унікальна структура",
        "✓ Додаткові модулі",
        "✓ CRM інтеграція",
        "✓ Telegram повідомлення",
        "✓ Підготовка під рекламу",
        "✓ SEO налаштування",
        "✓ Каталог або послуги",
        "✓ Будь-які додаткові блоки",
        "👉 Обговорити проект",
    ]
    return "\n".join(sections)


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
