from __future__ import annotations

from typing import Any


def build_website_v2_url(subdomain: str) -> str:
    return f"/w/{(subdomain or '').strip()}"


def get_website_v2_public_config(website: dict | Any) -> dict:
    config_live = (website or {}).get("config_live") or {}
    config_draft = (website or {}).get("config_draft") or {}
    return config_live or config_draft or {}


def _has_contact_method(seller: dict, config: dict) -> bool:
    seller_contacts = [
        seller.get("phone"),
        seller.get("telegram"),
        seller.get("viber"),
        seller.get("whatsapp"),
        seller.get("email"),
        seller.get("address"),
    ]
    contacts = config.get("contacts") or {}
    config_contacts = [
        contacts.get("phone"),
        contacts.get("email"),
        contacts.get("address"),
        (contacts.get("messengers") or {}).get("telegram"),
        (contacts.get("messengers") or {}).get("viber"),
        (contacts.get("messengers") or {}).get("whatsapp"),
    ]
    return any(str(v or "").strip() for v in [*seller_contacts, *config_contacts])


def build_catalog_website_context(website: dict, seller: dict) -> dict:
    config = get_website_v2_public_config(website)
    cars_count = int(seller.get("cars_count") or 0)
    products_count = int(seller.get("products_count") or 0)
    services_count = int(seller.get("services_count") or 0)
    has_hero = bool((config.get("hero") or {}).get("title") or (config.get("hero") or {}).get("subtitle"))
    has_contacts = _has_contact_method(seller, config)
    has_catalog_data = (cars_count + products_count) > 0

    missing: list[str] = []
    if not str((website or {}).get("name") or "").strip():
        missing.append("Назва сайту")
    if not str((website or {}).get("subdomain") or "").strip():
        missing.append("Субдомен")
    if not has_catalog_data:
        missing.append("Додайте авто або товари/запчастини в Каталог CRM")
    if not has_contacts:
        missing.append("Додайте хоча б один контакт")

    warnings: list[str] = []
    if services_count > 0:
        warnings.append("Послуги краще винести в окремий сайт-візитку.")

    return {
        "available_sections": ["hero", "search", "categories", "filters", "products", "cars", "vin_request", "contacts", "map", "footer"],
        "metrics": {
            "cars_count": cars_count,
            "products_count": products_count,
            "services_count": services_count,
            "has_contacts": has_contacts,
            "has_hero": has_hero,
            "has_catalog_data": has_catalog_data,
            "has_cars": cars_count > 0,
        },
        "missing_required_fields": missing,
        "publish_ready": len(missing) == 0,
        "warnings": warnings,
    }


def build_business_website_context(website: dict, seller: dict) -> dict:
    config = get_website_v2_public_config(website)
    services_count = int(seller.get("services_count") or 0)
    cars_count = int(seller.get("cars_count") or 0)
    products_count = int(seller.get("products_count") or 0)
    has_hero = bool((config.get("hero") or {}).get("title") or (config.get("hero") or {}).get("subtitle"))
    has_contacts = _has_contact_method(seller, config)

    missing: list[str] = []
    if not str((website or {}).get("name") or "").strip():
        missing.append("Назва сайту")
    if not str((website or {}).get("subdomain") or "").strip():
        missing.append("Субдомен")
    if services_count <= 0:
        missing.append("Додайте хоча б одну послугу")
    if not has_contacts:
        missing.append("Додайте хоча б один контакт")

    warnings: list[str] = []
    if cars_count > 0 or products_count > 0:
        warnings.append("Каталог запчастин краще винести в окремий сайт-магазин.")

    return {
        "available_sections": ["hero", "services", "service_details", "contact_cta", "contacts", "map", "footer"],
        "metrics": {
            "services_count": services_count,
            "cars_count": cars_count,
            "products_count": products_count,
            "has_contacts": has_contacts,
            "has_hero": has_hero,
            "has_services": services_count > 0,
        },
        "missing_required_fields": missing,
        "publish_ready": len(missing) == 0,
        "warnings": warnings,
    }


def build_website_v2_context(website: dict, seller: dict) -> dict:
    site_type = (website or {}).get("site_type") or "carpot_catalog"
    status = (website or {}).get("status") or "draft"
    config = get_website_v2_public_config(website)
    specialized = build_business_website_context(website, seller) if site_type == "carpot_business" else build_catalog_website_context(website, seller)
    return {
        "website": website,
        "seller": seller,
        "config": config,
        "site_type": site_type,
        "status": status,
        "public_url": build_website_v2_url((website or {}).get("subdomain") or ""),
        "dashboard_url": f"/crm/seller/{seller.get('crm_slug')}/websites/{website.get('id')}",
        "available_sections": specialized["available_sections"],
        "missing_required_fields": specialized["missing_required_fields"],
        "publish_ready": specialized["publish_ready"],
        "warnings": specialized["warnings"],
        "metrics": specialized["metrics"],
    }
