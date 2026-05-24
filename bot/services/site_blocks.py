from copy import deepcopy

SITE_BLOCK_REGISTRY = {
    "hero": {"label": "Перший екран", "module_key": "hero", "config_key": "hero", "editor_route": "hero", "template": "components/hero.html"},
    "services": {"label": "Послуги", "module_key": "services", "config_key": "services", "editor_route": "services", "template": "components/services.html"},
    "cars": {"label": "Авто на розборі", "module_key": "cars", "config_key": "cars", "editor_route": "cars", "template": "components/cars.html"},
    "catalog": {"label": "Каталог запчастин", "module_key": "catalog", "config_key": "products_catalog", "editor_route": "catalog", "template": "components/products.html"},
    "vin_request": {"label": "Підбір по VIN", "module_key": "vin_request", "config_key": "vin_request", "editor_route": "vin_request", "template": "components/vin_request.html"},
    "gallery": {"label": "Галерея", "module_key": "gallery", "config_key": "gallery", "editor_route": "gallery", "template": "components/gallery.html"},
    "about": {"label": "Про нас", "module_key": "about", "config_key": "about", "editor_route": "about", "template": "components/about.html"},
    "contacts": {"label": "Контакти", "module_key": "contacts", "config_key": "contacts", "editor_route": "contacts", "template": "components/contacts.html"},
    "map": {"label": "Карта", "module_key": "map", "config_key": "map", "editor_route": "map", "template": "components/map.html"},
    "footer": {"label": "Футер", "module_key": "footer", "config_key": "footer", "editor_route": "footer", "template": "components/footer.html"},
}


def get_site_block_registry() -> dict[str, dict[str, str]]:
    return deepcopy(SITE_BLOCK_REGISTRY)
