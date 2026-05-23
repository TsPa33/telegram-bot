from copy import deepcopy
from typing import Any


THEME_PRESETS: dict[str, dict[str, str]] = {
    "default": {"name": "CarPot Default", "scheme": "default", "accent": "#2563eb"},
    "dark_blue": {"name": "Dark Blue", "scheme": "electric_premium_dark", "accent": "#2563eb"},
    "dark_red": {"name": "Dark Red", "scheme": "parts_dark_red", "accent": "#dc2626"},
    "dark_green": {"name": "Dark Green", "scheme": "premium_dark", "accent": "#178582"},
    "premium_black": {"name": "Premium Black", "scheme": "premium_dark", "accent": "#BFA181"},
    "auto_service": {"name": "Auto Service", "scheme": "neon_dark", "accent": "#2272FF"},
    "tow_dark": {"name": "Tow Dark", "scheme": "parts_dark_red", "accent": "#f59e0b"},
    "sto_modern": {"name": "STO Modern", "scheme": "light_blue", "accent": "#00ABE4"},
    "light_blue": {"name": "Light Blue", "scheme": "light_blue", "accent": "#00ABE4"},
    "neon_dark": {"name": "Neon Dark", "scheme": "neon_dark", "accent": "#2272FF"},
    "premium_dark": {"name": "Premium Dark", "scheme": "premium_dark", "accent": "#178582"},
    "parts_dark_red": {"name": "Parts Dark Red", "scheme": "parts_dark_red", "accent": "#dc2626"},
    "electric_premium_dark": {"name": "Electric Premium", "scheme": "electric_premium_dark", "accent": "#2563eb"},
}


def get_theme_presets() -> dict[str, dict[str, str]]:
    return deepcopy(THEME_PRESETS)


_DEFAULT_SITE_CONFIG: dict[str, Any] = {

    "header": {
        "enabled": True,
        "title": "",
        "logo": "https://res.cloudinary.com/dyem6pgtd/image/upload/w_200/nllevu6x2rvr4w718f47",
        "background": None,
        "quick_buttons": [],
    },

    "hero": {
        "enabled": True,
        "title": "",
        "subtitle": "",
        "banners": [
            "https://res.cloudinary.com/dyem6pgtd/image/upload/c_fill,w_1200,h_400/pkkf5awehc8vdwbjo1ja",
            "https://res.cloudinary.com/dyem6pgtd/image/upload/c_fill,w_1200,h_400/uxh9fc5fjza7b2fn48fb",
            "https://res.cloudinary.com/dyem6pgtd/image/upload/c_fill,w_1200,h_400/bwmvj9y7ajswamgoafhn",
        ],
    },

    "categories": {
        "enabled": True,
    },

    "services": {
        "enabled": True,
        "title": "Послуги",
        "intro": "",
        "mode": "live",
    },

    "modules": {
        "hero": True,
        "services": True,
        "cars": True,
        "contacts": True,
        "map": True,
        "products": False,
        "pricing": False,
        "gallery": False,
        "works": False,
        "cta": False,
        "reviews": False,
        "footer": True,
    },

    "theme": {
        "scheme": "default",
    },

    "banner_cta": {
        "enabled": False,
        "text": "",
    },

    "price": {
        "enabled": False,
        "items": [],
    },

    "pricing": {
        "title": "Наші ціни",
        "subtitle": "Прозорі базові ціни. Остаточну вартість узгоджуємо після огляду авто або уточнення задачі.",
        "items": [],
    },

    "gallery": {
        "title": "Галерея",
        "items": [],
        "images": [],
    },

    "works": {
        "title": "Наші роботи",
        "subtitle": "Приклади задач, які бізнес може показати клієнтам для довіри перед заявкою.",
        "items": [],
    },

    "cta": {
        "title": "Потрібна консультація?",
        "text": "Напишіть нам у Telegram або залиште заявку — підкажемо рішення, терміни та орієнтовну вартість.",
        "telegram_text": "Telegram",
        "phone_text": "Подзвонити",
        "lead_text": "Залишити заявку",
    },

    "reviews": {
        "title": "Відгуки клієнтів",
        "subtitle": "Короткі рекомендації від клієнтів після сервісу, ремонту або виїзду.",
        "items": [],
    },

    "products": {
        "title": "Запчастини / товари",
        "intro": "",
        "subtitle": "Перевірені запчастини з розборки з підбором по VIN",
        "per_page": 12,
        "search_enabled": True,
        "categories": [],
        "items": [],
    },

    "layout": {
        "order": [
            "hero",
            "about",
            "services",
            "cars",
            "products",
            "gallery",
            "works",
            "contacts",
            "map",
            "reviews",
            "footer",
        ]
    },

    "about": {
        "enabled": False,
        "title": "Про нас",
        "text": "",
    },

    "cars": {
        "title": "Авто на розборі",
        "intro": "",
        "per_page": 6,
    },

    "map": {
        "enabled": True,
        "address": "",
        "lat": None,
        "lng": None,
    },

    # ================= CONTACTS =================

    "contacts": {

        "enabled": True,

        # ===== PHONES =====
        "phones": [],

        # ===== ADDRESS =====
        "address": "",

        # ===== MAP =====
        "map_embed": "",

        # ===== MESSENGERS =====
        "messengers": {
            "telegram": "",
            "whatsapp": "",
            "viber": "",
        },

        # ===== SOCIALS =====
        "socials": {
            "instagram": "",
            "facebook": "",
        },
    },

    "footer": {
        "enabled": True,
        "business_name": "",
        "text": "Всі права захищені",
    },
}


# =========================================================
# DEFAULT
# =========================================================

def get_default_site_config() -> dict:
    return deepcopy(_DEFAULT_SITE_CONFIG)


# =========================================================
# VALIDATE
# =========================================================

def validate_site_config(config: dict) -> bool:

    if not isinstance(config, dict):
        return False

    required = (
        "header",
        "contacts",
        "services",
        "map",
        "modules",
    )

    for key in required:

        if key not in config:
            return False

        if not isinstance(config[key], dict):
            return False

    return True


# =========================================================
# DEEP MERGE
# =========================================================

def _deep_merge_missing(target: dict, defaults: dict) -> dict:

    for key, default_value in defaults.items():

        if key not in target:
            target[key] = deepcopy(default_value)
            continue

        current_value = target[key]

        if isinstance(default_value, dict) and not isinstance(current_value, dict):
            target[key] = deepcopy(default_value)
            continue

        if isinstance(default_value, list) and not isinstance(current_value, list):
            target[key] = deepcopy(default_value)
            continue

        if isinstance(current_value, dict) and isinstance(default_value, dict):
            _deep_merge_missing(current_value, default_value)

    return target


# =========================================================
# NORMALIZE
# =========================================================

def _normalize_config(config: dict) -> dict:

    # ===== MODULES =====

    default_modules = _DEFAULT_SITE_CONFIG["modules"]

    modules = config.get("modules")

    if not isinstance(modules, dict):

        config["modules"] = deepcopy(default_modules)

    else:

        config["modules"] = {
            key: bool(modules.get(key, default_enabled))
            for key, default_enabled in default_modules.items()
        }

    # ===== THEME =====

    theme = config.get("theme")

    if not isinstance(theme, dict):
        config["theme"] = deepcopy(_DEFAULT_SITE_CONFIG["theme"])
    elif theme.get("scheme") not in THEME_PRESETS:
        theme["scheme"] = "default"

    # ===== HERO =====

    hero = config.setdefault("hero", {})
    banners = hero.get("banners")
    if not isinstance(banners, list):
        banners = []
    normalized_banners = []
    for banner in banners:
        if isinstance(banner, str):
            image = banner.strip()
            if image:
                normalized_banners.append({"image": image, "fit": "cover", "position": "center"})
        elif isinstance(banner, dict):
            image = str(banner.get("image") or banner.get("url") or "").strip()
            if not image:
                continue
            fit = str(banner.get("fit") or "cover").strip().lower()
            if fit not in {"cover", "contain", "fill"}:
                fit = "cover"
            position = str(banner.get("position") or "center").strip().lower()
            if position not in {"center", "top", "bottom"}:
                position = "center"
            normalized_banners.append({"image": image, "fit": fit, "position": position})
    hero["banners"] = normalized_banners

    # ===== PRICE =====

    if not isinstance(config.get("price", {}).get("items"), list):
        config.setdefault("price", {})["items"] = []

    # ===== NEW OPTIONAL MODULE DATA =====

    for section_name, list_key in {
        "pricing": "items",
        "gallery": "images",
        "works": "items",
        "reviews": "items",
    }.items():
        section = config.setdefault(section_name, {})
        if not isinstance(section.get(list_key), list):
            section[list_key] = []

    if not isinstance(config.get("cta"), dict):
        config["cta"] = deepcopy(_DEFAULT_SITE_CONFIG["cta"])

    # ===== PRODUCTS =====

    products = config.setdefault("products", {})

    if not isinstance(config.get("about"), dict):
        config["about"] = deepcopy(_DEFAULT_SITE_CONFIG["about"])
    if not isinstance(config.get("cars"), dict):
        config["cars"] = deepcopy(_DEFAULT_SITE_CONFIG["cars"])
    if not isinstance(config.get("gallery"), dict):
        config["gallery"] = deepcopy(_DEFAULT_SITE_CONFIG["gallery"])
    if not isinstance(config.get("footer"), dict):
        config["footer"] = deepcopy(_DEFAULT_SITE_CONFIG["footer"])

    if not isinstance(products.get("categories"), list):
        products["categories"] = []

    if not isinstance(products.get("items"), list):
        products["items"] = []
    per_page = products.get("per_page")
    if not isinstance(per_page, int):
        products["per_page"] = 12
    else:
        products["per_page"] = max(3, min(48, per_page))
    products["search_enabled"] = bool(products.get("search_enabled", True))

    cars = config.setdefault("cars", {})
    cars_per_page = cars.get("per_page")
    if not isinstance(cars_per_page, int):
        cars["per_page"] = 6
    else:
        cars["per_page"] = max(3, min(48, cars_per_page))

    layout = config.setdefault("layout", {})
    default_order = _DEFAULT_SITE_CONFIG["layout"]["order"]
    raw_order = layout.get("order")
    if not isinstance(raw_order, list):
        raw_order = []
    normalized_order = []
    for key in raw_order:
        if isinstance(key, str) and key in default_order and key not in normalized_order:
            normalized_order.append(key)
    for key in default_order:
        if key not in normalized_order:
            normalized_order.append(key)
    layout["order"] = normalized_order

    # ===== CONTACTS =====

    contacts = config.setdefault("contacts", {})

    if not isinstance(contacts.get("phones"), list):
        contacts["phones"] = []

    if not isinstance(contacts.get("messengers"), dict):
        contacts["messengers"] = {
            "telegram": "",
            "whatsapp": "",
            "viber": "",
        }

    if not isinstance(contacts.get("socials"), dict):
        contacts["socials"] = {
            "instagram": "",
            "facebook": "",
        }

    return config


# =========================================================
# MERGE
# =========================================================

def merge_with_default(config: dict) -> dict:

    if not isinstance(config, dict):
        return get_default_site_config()

    merged = deepcopy(config)

    merged = _deep_merge_missing(
        merged,
        _DEFAULT_SITE_CONFIG
    )

    merged = _normalize_config(merged)

    return merged
