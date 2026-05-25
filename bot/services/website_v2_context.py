from __future__ import annotations

import json
from typing import Any


def build_website_v2_url(subdomain: str) -> str:
    return f"/w/{(subdomain or '').strip()}"


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def get_website_v2_public_config(website: dict | Any) -> dict:
    row = website or {}
    config_live = _as_dict(row.get("config_live"))
    config_draft = _as_dict(row.get("config_draft"))
    raw = config_live or config_draft
    nested = _as_dict(raw.get("website_v2"))
    base = nested or raw
    return {
        "hero": _as_dict(base.get("hero")),
        "catalog": _as_dict(base.get("catalog") or base.get("products_catalog")),
        "business": _as_dict(base.get("business") or base.get("services")),
        "contacts": _as_dict(base.get("contacts")),
        "map": _as_dict(base.get("map")),
        "seo": _as_dict(base.get("seo")),
        "publication": _as_dict(base.get("publication")),
    }


def _has_contact_method(seller: dict, config: dict) -> bool:
    seller_contacts = [
        seller.get("phone"),
        seller.get("telegram"),
        seller.get("viber"),
        seller.get("whatsapp"),
        seller.get("email"),
        seller.get("address"),
    ]
    contacts = config.get("contacts") if isinstance(config.get("contacts"), dict) else {}
    config_contacts = [
        contacts.get("phone"),
        contacts.get("email"),
        contacts.get("address"),
        (contacts.get("messengers") or {}).get("telegram"),
        (contacts.get("messengers") or {}).get("viber"),
        (contacts.get("messengers") or {}).get("whatsapp"),
    ]
    return any(str(v or "").strip() for v in [*seller_contacts, *config_contacts])


def detect_website_v2_contacts(config: dict, seller: dict) -> dict:
    contacts = config.get("contacts") if isinstance(config.get("contacts"), dict) else {}
    messengers = contacts.get("messengers") if isinstance(contacts.get("messengers"), dict) else {}
    phones_raw = contacts.get("phones")
    phones = [str(value).strip() for value in phones_raw] if isinstance(phones_raw, list) else []
    phone = str(contacts.get("phone") or "").strip()
    telegram = str(contacts.get("telegram") or messengers.get("telegram") or "").strip()
    viber = str(contacts.get("viber") or messengers.get("viber") or "").strip()
    whatsapp = str(contacts.get("whatsapp") or messengers.get("whatsapp") or "").strip()
    website = str(contacts.get("website") or "").strip()
    has_website_contacts = any([phone, *phones, telegram, viber, whatsapp, website])
    if has_website_contacts:
        return {
            "has_contacts": True,
            "source": "website",
            "phone": phone,
            "phones": phones,
            "telegram": telegram,
            "viber": viber,
            "whatsapp": whatsapp,
            "website": website,
        }

    seller_phone = str(seller.get("phone") or seller.get("contact_phone") or "").strip()
    seller_telegram = str(seller.get("telegram") or seller.get("username") or "").strip()
    seller_viber = str(seller.get("viber") or "").strip()
    seller_whatsapp = str(seller.get("whatsapp") or "").strip()
    seller_website = str(seller.get("website") or "").strip()
    has_seller_contacts = any([seller_phone, seller_telegram, seller_viber, seller_whatsapp, seller_website])
    return {
        "has_contacts": has_seller_contacts,
        "source": "seller_profile" if has_seller_contacts else "none",
        "phone": seller_phone,
        "phones": [seller_phone] if seller_phone else [],
        "telegram": seller_telegram,
        "viber": seller_viber,
        "whatsapp": seller_whatsapp,
        "website": seller_website,
    }


def build_catalog_website_context(website: dict, seller: dict) -> dict:
    config = get_website_v2_public_config(website)
    raw_cars = seller.get("cars_items") or []
    raw_products = seller.get("catalog_items") or []
    if not isinstance(raw_products, list):
        raw_products = []
    categories = sorted(
        {
            item.get("category", "").strip()
            for item in raw_products
            if isinstance(item, dict) and item.get("category")
        }
    )
    cars_count = int(seller.get("cars_count") or len(raw_cars) or 0)
    products_count = int(seller.get("products_count") or len(raw_products) or 0)
    services_count = int(seller.get("services_count") or 0)
    hero = config.get("hero") if isinstance(config.get("hero"), dict) else {}
    has_hero = bool(hero.get("title") or hero.get("subtitle"))
    website_contacts = detect_website_v2_contacts(config, seller)
    has_contacts = bool(website_contacts.get("has_contacts"))
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
        "catalog_items": raw_products[:12],
        "cars_items": raw_cars[:6],
        "categories": categories,
        "has_catalog_items": len(raw_products) > 0,
        "website_contacts": website_contacts,
        "missing_required_fields": missing,
        "publish_ready": len(missing) == 0,
        "warnings": warnings,
    }


def build_business_website_context(website: dict, seller: dict) -> dict:
    config = get_website_v2_public_config(website)
    raw_services = seller.get("services_items") or []
    services_count = int(seller.get("services_count") or len(raw_services) or 0)
    cars_count = int(seller.get("cars_count") or 0)
    products_count = int(seller.get("products_count") or 0)
    hero = config.get("hero") if isinstance(config.get("hero"), dict) else {}
    has_hero = bool(hero.get("title") or hero.get("subtitle"))
    website_contacts = detect_website_v2_contacts(config, seller)
    has_contacts = bool(website_contacts.get("has_contacts"))

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
        "services_items": raw_services[:9],
        "website_contacts": website_contacts,
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
        "catalog_items": specialized.get("catalog_items", []),
        "cars_items": specialized.get("cars_items", []),
        "categories": specialized.get("categories", []),
        "has_catalog_items": specialized.get("has_catalog_items", False),
        "services_items": specialized.get("services_items", []),
        "website_contacts": specialized.get("website_contacts", {"has_contacts": False, "source": "none"}),
    }
