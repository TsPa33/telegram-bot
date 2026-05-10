from copy import deepcopy
from typing import Any


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
        "mode": "live",
    },

    "modules": {
        "services": True,
        "cars": True,
        "contacts": True,
        "map": True,
        "products": False,
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

    "products": {
        "title": "Каталог автозапчастин",
        "subtitle": "Перевірені запчастини з розборки з підбором по VIN",
        "categories": [],
        "items": [],
    },

    "about": {
        "enabled": False,
        "text": "",
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
        "text": "",
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
    elif theme.get("scheme") not in {"default", "light_blue", "neon_dark", "premium_dark"}:
        theme["scheme"] = "default"

    # ===== HERO =====

    if not isinstance(config.get("hero", {}).get("banners"), list):
        config.setdefault("hero", {})["banners"] = []

    # ===== PRICE =====

    if not isinstance(config.get("price", {}).get("items"), list):
        config.setdefault("price", {})["items"] = []

    # ===== PRODUCTS =====

    products = config.setdefault("products", {})

    if not isinstance(products.get("categories"), list):
        products["categories"] = []

    if not isinstance(products.get("items"), list):
        products["items"] = []

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
