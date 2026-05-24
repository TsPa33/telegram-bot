from copy import deepcopy

SITE_BLOCK_REGISTRY = {
    "hero": {"label": "Перший екран", "module_key": "hero", "config_key": "hero"},
    "about": {"label": "Про нас", "module_key": "about", "config_key": "about"},
    "cars": {"label": "Авто на розборі", "module_key": "cars", "config_key": "cars"},
    "products_catalog": {"label": "Каталог запчастин", "module_key": "products_catalog", "config_key": "products_catalog"},
    "vin_request": {"label": "Підбір по VIN", "module_key": "vin_request", "config_key": "vin_request"},
    "services": {"label": "Послуги", "module_key": "services", "config_key": "services"},
    "gallery": {"label": "Галерея", "module_key": "gallery", "config_key": "gallery"},
    "contacts": {"label": "Контакти", "module_key": "contacts", "config_key": "contacts"},
    "map": {"label": "Карта", "module_key": "map", "config_key": "map"},
    "footer": {"label": "Футер", "module_key": "footer", "config_key": "footer"},
}


def get_site_block_registry() -> dict[str, dict[str, str]]:
    return deepcopy(SITE_BLOCK_REGISTRY)
