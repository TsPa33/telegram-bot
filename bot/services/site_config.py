from copy import deepcopy
from typing import Any


_DEFAULT_SITE_CONFIG: dict[str, Any] = {
    "header": {
        "enabled": True,
        "title": "",
        "logo": "https://res.cloudinary.com/dyem6pgtd/image/upload/w_200/pkkf5awehc8vdwbjo1ja",
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
    },

    "banner_cta": {
        "enabled": False,
        "text": "",
    },

    "price": {
        "enabled": False,
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

    "contacts": {
        "enabled": True,
        "phone": "",
        "telegram": "",
        "address": "",
        "map_embed": "",
    },

    "footer": {
        "enabled": True,
        "text": "",
    },
}


def get_default_site_config() -> dict:
    return deepcopy(_DEFAULT_SITE_CONFIG)


def validate_site_config(config: dict) -> bool:
    if not isinstance(config, dict):
        return False

    required = ("header", "contacts", "services", "map", "modules")

    for key in required:
        if key not in config or not isinstance(config[key], dict):
            return False

    return True


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


def _normalize_config(config: dict) -> dict:
    # ===== MODULES =====
    default_modules = _DEFAULT_SITE_CONFIG["modules"]
    modules = config.get("modules")

    if not isinstance(modules, dict):
        config["modules"] = deepcopy(default_modules)
    else:
        config["modules"] = {
            key: bool(modules.get(key, True))
            for key in default_modules
        }

    # ===== HERO.BANNERS =====
    if not isinstance(config.get("hero", {}).get("banners"), list):
        config.setdefault("hero", {})["banners"] = []

    # ===== PRICE.ITEMS =====
    if not isinstance(config.get("price", {}).get("items"), list):
        config.setdefault("price", {})["items"] = []

    return config


def merge_with_default(config: dict) -> dict:
    if not isinstance(config, dict):
        return get_default_site_config()

    merged = deepcopy(config)

    merged = _deep_merge_missing(merged, _DEFAULT_SITE_CONFIG)
    merged = _normalize_config(merged)

    return merged
