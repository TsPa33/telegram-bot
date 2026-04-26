from copy import deepcopy
from typing import Any


_DEFAULT_SITE_CONFIG: dict[str, Any] = {
    "header": {
        "enabled": True,
        "title": "",
        "logo": None,
        "background": None,
        "quick_buttons": [],
    },
    "hero": {
        "enabled": True,
        "title": "",
        "subtitle": "",
        "banners": [],
    },
    "categories": {
        "enabled": True,
    },
    "services": {
        "enabled": True,
        "mode": "live",
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

    required_enabled_sections = ("header", "contacts", "services", "map")

    for section_name in required_enabled_sections:
        section = config.get(section_name)

        if not isinstance(section, dict):
            return False

        if section.get("enabled") is not True:
            return False

    return True


def _deep_merge_missing(target: dict, defaults: dict) -> dict:
    for key, default_value in defaults.items():
        if key not in target:
            target[key] = deepcopy(default_value)
            continue

        current_value = target[key]

        # ❗ FIX: якщо тип не dict — замінюємо
        if isinstance(default_value, dict) and not isinstance(current_value, dict):
            target[key] = deepcopy(default_value)
            continue

        if isinstance(current_value, dict) and isinstance(default_value, dict):
            _deep_merge_missing(current_value, default_value)

    return target


def merge_with_default(config: dict) -> dict:
    if not isinstance(config, dict):
        return get_default_site_config()

    merged_config = deepcopy(config)
    return _deep_merge_missing(merged_config, _DEFAULT_SITE_CONFIG)