from copy import deepcopy
from typing import Any

CANONICAL_TEMPLATE_IDS = (
    "universal_classic",
    "universal_catalog",
    "universal_premium",
)

TEMPLATE_LEGACY_ALIASES: dict[str, str] = {
    "service_classic": "universal_classic",
    "dismantler_classic": "universal_classic",
    "service_modern": "universal_catalog",
    "dismantler_catalog": "universal_catalog",
    "service_premium": "universal_premium",
    "dismantler_premium": "universal_premium",
}

SITE_TEMPLATE_META: dict[str, dict[str, str]] = {
    "universal_classic": {"label": "Universal Sales", "concept": "Universal Sales"},
    "universal_catalog": {"label": "Calm Marketplace", "concept": "Calm Marketplace"},
    "universal_premium": {"label": "Brutal Metallic", "concept": "Brutal Metallic"},
}

CANONICAL_COLOR_SCHEME_IDS = (
    "graphite_red",
    "steel_blue",
    "black_gold",
    "clean_navy",
    "soft_green",
)

COLOR_SCHEME_LEGACY_ALIASES: dict[str, str] = {
    "dark_red": "graphite_red",
    "dark_blue": "steel_blue",
    "graphite": "graphite_red",
    "black_gold": "black_gold",
    "light_minimal": "clean_navy",
}

SITE_COLOR_SCHEME_META: dict[str, dict[str, str]] = {
    "graphite_red": {"label": "Graphite Red"},
    "steel_blue": {"label": "Steel Blue"},
    "black_gold": {"label": "Black Gold"},
    "clean_navy": {"label": "Clean Navy"},
    "soft_green": {"label": "Soft Green"},
}

CANONICAL_SECTION_IDS = (
    "hero",
    "about",
    "services",
    "catalog",
    "cars",
    "gallery",
    "vin",
    "contacts",
    "map",
    "footer",
)

SECTION_LEGACY_ALIASES: dict[str, str] = {
    "products": "catalog",
    "products_catalog": "catalog",
    "vin_request": "vin",
}

SITE_SECTION_META: dict[str, dict[str, str]] = {
    "hero": {"label": "Hero"},
    "about": {"label": "About"},
    "services": {"label": "Services"},
    "catalog": {"label": "Catalog"},
    "cars": {"label": "Cars"},
    "gallery": {"label": "Gallery"},
    "vin": {"label": "VIN"},
    "contacts": {"label": "Contacts"},
    "map": {"label": "Map"},
    "footer": {"label": "Footer"},
}

TEMPLATE_DEFAULT_SECTIONS_ORDER: dict[str, list[str]] = {
    "universal_premium": ["hero", "about", "catalog", "cars", "services", "gallery", "vin", "contacts", "map", "footer"],
    "universal_catalog": ["hero", "catalog", "cars", "vin", "gallery", "about", "contacts", "map", "footer"],
    "universal_classic": ["hero", "about", "services", "catalog", "cars", "gallery", "vin", "contacts", "map", "footer"],
}


def normalize_template_id(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    mapped = TEMPLATE_LEGACY_ALIASES.get(raw, raw)
    if mapped not in CANONICAL_TEMPLATE_IDS:
        return "universal_classic"
    return mapped


def normalize_color_scheme(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    mapped = COLOR_SCHEME_LEGACY_ALIASES.get(raw, raw)
    if mapped not in CANONICAL_COLOR_SCHEME_IDS:
        return "graphite_red"
    return mapped


def get_legacy_color_scheme_id(value: str | None) -> str:
    canonical = normalize_color_scheme(value)
    legacy_by_canonical = {
        "graphite_red": "dark_red",
        "steel_blue": "dark_blue",
        "black_gold": "black_gold",
        "clean_navy": "light_minimal",
        "soft_green": "graphite",
    }
    return legacy_by_canonical.get(canonical, "dark_red")


def normalize_section_id(value: str | None) -> str | None:
    raw = str(value or "").strip().lower()
    mapped = SECTION_LEGACY_ALIASES.get(raw, raw)
    if mapped in CANONICAL_SECTION_IDS:
        return mapped
    return None


def normalize_sections_order(value: list | None, template_id: str | None = None) -> list[str]:
    canonical_template_id = normalize_template_id(template_id)
    default_order = list(TEMPLATE_DEFAULT_SECTIONS_ORDER.get(canonical_template_id, TEMPLATE_DEFAULT_SECTIONS_ORDER["universal_classic"]))
    raw_list = value if isinstance(value, list) else []
    normalized: list[str] = []
    for raw in raw_list:
        section_id = normalize_section_id(raw if isinstance(raw, str) else None)
        if section_id and section_id not in normalized:
            normalized.append(section_id)

    if not normalized:
        return default_order

    for section_id in default_order:
        if section_id not in normalized:
            normalized.append(section_id)

    without_footer = [s for s in normalized if s != "footer"]
    if "footer" in normalized:
        without_footer.append("footer")
    return without_footer

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

DEFAULT_LAUNCH_PRESET_ID = "automotive_universal"

LAUNCH_PRESETS: dict[str, dict[str, Any]] = {
    "automotive_universal": {
        "modules": {
            "hero": True,
            "about": True,
            "services": True,
            "catalog": True,
            "cars": True,
            "gallery": True,
            "vin": True,
            "contacts": True,
            "map": True,
            "footer": True,
        },
        "hero": {
            "title": "Автозапчастини та автопослуги в одному місці",
            "subtitle": "Допоможемо швидко знайти потрібне рішення для вашого авто.",
            "button_text": "Звʼязатися",
            "button_secondary_text": "Переглянути пропозиції",
            "trust_items": ["Швидкий звʼязок", "Підбір під авто", "Актуальна наявність"],
        },
        "about": {
            "title": "Про нас",
            "description": "Ми працюємо з автотоварами та послугами для автомобілів. На сайті ви можете переглянути пропозиції, залишити заявку або швидко звʼязатися з продавцем.",
            "advantages": ["Швидкий звʼязок", "Зручний підбір", "Актуальні пропозиції"],
        },
        "services": {
            "title": "Послуги",
            "description": "Підберемо рішення під ваш запит та уточнимо наявність у зручному форматі.",
            "items": [
                {"title": "Підбір запчастин", "description": "Підбір за VIN, маркою або артикулом.", "label": "за запитом"},
                {"title": "Двигуни та КПП", "description": "Допоможемо підібрати вузли та комплектуючі.", "label": "за запитом"},
                {"title": "Кузовні деталі", "description": "Крила, бампери, двері та інші кузовні елементи.", "label": "за запитом"},
                {"title": "Автооптика", "description": "Фари, ліхтарі, протитуманні блоки та супутні деталі.", "label": "за запитом"},
                {"title": "Запчастини з розборки", "description": "Актуальні пропозиції по вживаних деталях.", "label": "за запитом"},
                {"title": "Консультація по наявності", "description": "Швидко підкажемо, що доступно прямо зараз.", "label": "за запитом"},
            ],
        },
        "catalog": {
            "title": "Каталог пропозицій",
            "description": "Перегляньте доступні товари або залиште запит на підбір.",
            "layout": "grid",
            "per_page": 6,
            "cta_label": "Уточнити наявність",
            "featured_categories": ["Двигун", "Кузов", "Оптика"],
        },
        "cars": {
            "title": "Авто в наявності",
            "description": "Список актуальних авто оновлюється. Залиште запит на потрібну модель.",
            "layout": "grid",
            "per_page": 6,
            "cta_label": "Уточнити наявність",
        },
        "gallery": {
            "title": "Галерея",
            "description": "Приклади товарів і робіт, які можна замовити або уточнити.",
            "layout": "masonry",
            "images": [],
            "items": [],
        },
        "vin": {
            "title": "Не знаєте, яка деталь підходить?",
            "description": "Надішліть VIN-код або опис авто — ми допоможемо з підбором.",
            "button_label": "Надіслати запит",
        },
        "vin_request": {
            "title": "Не знаєте, яка деталь підходить?",
            "text": "Надішліть VIN-код або опис авто — ми допоможемо з підбором.",
            "button_text": "Надіслати запит",
        },
        "footer": {
            "business_name": "",
            "text": "Підбір автотоварів та послуг для вашого авто.",
            "powered_by": "Працює на CarPot",
        },
    },
}

_CRITICAL_STRING_FIELDS = {
    ("hero", "title"), ("hero", "subtitle"), ("hero", "button_text"), ("hero", "button_secondary_text"),
    ("about", "title"), ("about", "description"),
    ("services", "title"), ("services", "description"),
    ("catalog", "title"), ("catalog", "description"), ("catalog", "cta_label"),
    ("cars", "title"), ("cars", "description"), ("cars", "cta_label"),
    ("gallery", "title"), ("gallery", "description"),
    ("vin", "title"), ("vin", "description"), ("vin", "button_label"),
    ("vin_request", "title"), ("vin_request", "text"), ("vin_request", "button_text"),
}

def get_theme_presets() -> dict[str, dict[str, str]]:
    return deepcopy(THEME_PRESETS)


def get_launch_preset(preset_id: str | None = None) -> dict[str, Any]:
    key = str(preset_id or DEFAULT_LAUNCH_PRESET_ID).strip().lower()
    preset = LAUNCH_PRESETS.get(key) or LAUNCH_PRESETS[DEFAULT_LAUNCH_PRESET_ID]
    return deepcopy(preset)


def _merge_launch_defaults(target: dict, defaults: dict, *, path: tuple[str, ...], initial_creation: bool) -> dict:
    for key, default_value in defaults.items():
        current_path = path + (key,)
        if key not in target:
            target[key] = deepcopy(default_value)
            continue
        current_value = target[key]
        if isinstance(default_value, dict):
            if not isinstance(current_value, dict):
                target[key] = deepcopy(default_value)
            else:
                _merge_launch_defaults(current_value, default_value, path=current_path, initial_creation=initial_creation)
            continue
        if isinstance(default_value, str):
            if isinstance(current_value, str):
                if not current_value.strip() and current_path in _CRITICAL_STRING_FIELDS:
                    target[key] = default_value
            elif current_value is None:
                target[key] = default_value
            continue
        if isinstance(default_value, list):
            if current_value is None:
                target[key] = deepcopy(default_value)
            continue
        if key == "modules" and isinstance(default_value, dict) and isinstance(current_value, dict) and initial_creation:
            for mk, mv in default_value.items():
                current_value.setdefault(mk, bool(mv))
            continue
        if current_value is None:
            target[key] = deepcopy(default_value)
    return target


def apply_launch_defaults(config: dict, *, preset_id: str | None = None, initial_creation: bool = False) -> dict:
    if not isinstance(config, dict):
        return config
    preset = get_launch_preset(preset_id)
    merged = deepcopy(config)
    if initial_creation:
        merged_modules = merged.setdefault("modules", {})
        if isinstance(merged_modules, dict):
            for key, value in (preset.get("modules") or {}).items():
                merged_modules.setdefault(key, bool(value))
    return _merge_launch_defaults(merged, preset, path=tuple(), initial_creation=initial_creation)


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
        "catalog": False,
        "vin_request": False,
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

    "gallery": {"title": "Галерея", "intro": "", "items": [], "images": []},

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

    "products_catalog": {
        "title": "Запчастини / товари",
        "intro": "",
        "subtitle": "Перевірені запчастини з розборки з підбором по VIN",
        "per_page": 12,
        "search_enabled": True,
        "categories": [],
        "items": [],
    },
    "vin_request": {
        "title": "Підбір по VIN",
        "text": "Залиште запит і ми підберемо потрібну деталь.",
        "button_text": "Підібрати запчастину",
        "fields": {
            "vin_brand_model": "VIN / марка / модель",
            "part_name": "Назва деталі",
            "name": "Імʼя",
            "phone": "Телефон",
        },
    },

    "layout": {
        "order": [
            "hero",
            "catalog",
            "vin_request",
            "cars",
            "services",
            "gallery",
            "about",
            "contacts",
            "map",
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
    modules = config.get("modules")
    incoming_modules = modules if isinstance(modules, dict) else {}
    normalized_modules = deepcopy(incoming_modules)
    canonical_module_defaults = {
        "hero": True,
        "about": False,
        "services": True,
        "catalog": False,
        "cars": True,
        "gallery": False,
        "vin": False,
        "contacts": True,
        "map": True,
        "footer": True,
    }
    if "catalog" not in normalized_modules:
        if "catalog" in incoming_modules:
            normalized_modules["catalog"] = bool(incoming_modules.get("catalog"))
        elif "products" in incoming_modules:
            normalized_modules["catalog"] = bool(incoming_modules.get("products"))
        elif "products_catalog" in incoming_modules:
            normalized_modules["catalog"] = bool(incoming_modules.get("products_catalog"))
    if "vin" not in normalized_modules:
        if "vin" in incoming_modules:
            normalized_modules["vin"] = bool(incoming_modules.get("vin"))
        elif "vin_request" in incoming_modules:
            normalized_modules["vin"] = bool(incoming_modules.get("vin_request"))
    for key, default_enabled in canonical_module_defaults.items():
        if key not in normalized_modules:
            normalized_modules[key] = bool(default_enabled)
        else:
            normalized_modules[key] = bool(normalized_modules.get(key))
    config["modules"] = normalized_modules

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

    products = config.get("products_catalog")
    if not isinstance(products, dict) and isinstance(config.get("products"), dict):
        products = deepcopy(config.get("products"))
        config["products_catalog"] = products
    products = config.setdefault("products_catalog", {})

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

    if not isinstance(config.get("vin_request"), dict):
        config["vin_request"] = deepcopy(_DEFAULT_SITE_CONFIG["vin_request"])
    if not isinstance(config.get("vin"), dict):
        config["vin"] = deepcopy(config.get("vin_request") or _DEFAULT_SITE_CONFIG["vin_request"])

    design = config.get("design")
    if not isinstance(design, dict):
        design = {}
    design["template_id"] = normalize_template_id(design.get("template_id"))
    design["color_scheme"] = normalize_color_scheme(design.get("color_scheme"))
    design["color_scheme_legacy"] = get_legacy_color_scheme_id(design.get("color_scheme"))
    config["design"] = design

    layout = config.setdefault("layout", {})
    layout_order = layout.get("order")
    sections_order_raw = config.get("sections_order")
    source_order = sections_order_raw if isinstance(sections_order_raw, list) else layout_order
    normalized_sections = normalize_sections_order(source_order, template_id=design.get("template_id"))
    config["sections_order"] = normalized_sections
    layout["order"] = normalized_sections

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
    merged = apply_launch_defaults(merged, initial_creation=False)

    return merged
