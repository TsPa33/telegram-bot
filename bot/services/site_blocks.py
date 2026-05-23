from copy import deepcopy

SITE_BLOCK_REGISTRY = {
    "hero": {"label": "Перший екран", "module_key": "hero", "config_key": "hero"},
    "about": {"label": "Про нас", "module_key": "about", "config_key": "about"},
    "cars": {"label": "Авто на розборі", "module_key": "cars", "config_key": "cars"},
    "products": {"label": "Товари / запчастини", "module_key": "products", "config_key": "products"},
    "services": {"label": "Послуги", "module_key": "services", "config_key": "services"},
    "gallery": {"label": "Галерея", "module_key": "gallery", "config_key": "gallery"},
    "contacts": {"label": "Контакти", "module_key": "contacts", "config_key": "contacts"},
    "map": {"label": "Карта", "module_key": "map", "config_key": "map"},
    "footer": {"label": "Футер", "module_key": "footer", "config_key": "footer"},
    "reviews": {"label": "Відгуки", "module_key": "reviews", "config_key": "reviews"},
    "cta": {"label": "Заклик до дії", "module_key": "cta", "config_key": "cta"},
}


def get_site_block_registry() -> dict[str, dict[str, str]]:
    return deepcopy(SITE_BLOCK_REGISTRY)

