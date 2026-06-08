from __future__ import annotations

import json
import logging
from typing import Any
logger = logging.getLogger(__name__)


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


def _merge_dicts(base: dict, override: dict) -> dict:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _has_meaningful_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_meaningful_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_meaningful_value(item) for item in value)
    return value not in (None, "", [], {})


def _canonicalize_hero_aliases(hero: dict) -> dict:
    normalized = dict(hero or {})
    banner_url = str(normalized.get("banner_url") or "").strip()
    primary_cta = str(normalized.get("primary_cta") or "").strip()
    if banner_url and not str(normalized.get("image_url") or "").strip():
        normalized["image_url"] = banner_url
    if primary_cta and not str(normalized.get("cta_text") or "").strip():
        normalized["cta_text"] = primary_cta
    return normalized


def _normalize_hero_config(hero: dict, source_path: str) -> dict:
    normalized = dict(hero or {})
    banners = normalized.get("banners") if isinstance(normalized.get("banners"), list) else []
    image_url = str(
        normalized.get("image_url")
        or normalized.get("banner_url")
        or ""
    ).strip()

    resolved_banners = [banner for banner in banners if isinstance(banner, dict)]
    if image_url and not any(str(banner.get("image") or "").strip() for banner in resolved_banners):
        resolved_banners = [{"image": image_url}, *resolved_banners]
    if image_url:
        normalized["image_url"] = image_url
    normalized["banners"] = resolved_banners

    cta_text = str(normalized.get("cta_text") or normalized.get("primary_cta") or "").strip()
    if cta_text:
        normalized["cta_text"] = cta_text

    logger.info(
        "Website V2 hero context: source=%s image_resolved=%s cta_resolved=%s",
        source_path,
        bool(image_url or any(str(banner.get("image") or "").strip() for banner in resolved_banners)),
        bool(cta_text),
    )
    return normalized


def get_website_v2_public_config(website: dict | Any) -> dict:
    row = website or {}
    config_live = _as_dict(row.get("config_live"))
    config_draft = _as_dict(row.get("config_draft"))
    raw = config_live or config_draft
    nested = _as_dict(raw.get("website_v2"))
    base = nested or raw
    nested_hero = _canonicalize_hero_aliases(_as_dict(base.get("hero")))
    top_level_hero = _canonicalize_hero_aliases(_as_dict(raw.get("hero")))
    nested_has_content = _has_meaningful_value(nested_hero)
    top_level_has_content = _has_meaningful_value(top_level_hero)
    hero_source = "website_v2.hero" if nested_has_content else ("top_level.hero" if top_level_has_content else "none")
    hero = _normalize_hero_config(_merge_dicts(top_level_hero, nested_hero), hero_source)
    return {
        "hero": hero,
        "catalog": _as_dict(base.get("catalog") or base.get("products_catalog")),
        "business": _as_dict(base.get("business") or base.get("services")),
        "contacts": _as_dict(base.get("contacts")),
        "map": _as_dict(base.get("map")),
        "seo": _as_dict(base.get("seo")),
        "publication": _as_dict(base.get("publication")),
    }



def _normalize_contact_phone_href(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    has_plus = raw.startswith("+")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    if has_plus:
        return f"+{digits}"
    if len(digits) == 10 and digits.startswith("0"):
        return f"+38{digits}"
    if len(digits) == 12 and digits.startswith("380"):
        return f"+{digits}"
    if len(digits) >= 7:
        return f"+{digits}"
    return ""


def _normalize_telegram_href(value: Any) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    if raw.startswith("http://") or raw.startswith("https://"):
        username = raw.rstrip("/").split("/")[-1].strip()
        return raw, f"@{username.lstrip('@')}" if username else raw
    username = raw.lstrip("@").strip().strip("/")
    if not username:
        return "", ""
    return f"https://t.me/{username}", f"@{username}"


def _normalize_external_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return f"https://{raw}"


def _normalize_email_href(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or "@" not in raw:
        return ""
    return f"mailto:{raw}"


def _build_contact_actions(contact: dict) -> dict:
    primary_phone = str(contact.get("phone") or "").strip()
    phones = [str(value or "").strip() for value in (contact.get("phones") or []) if str(value or "").strip()]
    ordered_phones = []
    for value in [primary_phone, *phones]:
        if value and value not in ordered_phones:
            ordered_phones.append(value)
    phone_items = [
        {"icon": "☎", "label": "Телефон", "value": value, "href": f"tel:{href}"}
        for value in ordered_phones
        for href in [_normalize_contact_phone_href(value)]
        if href
    ]
    telegram_href, telegram_label = _normalize_telegram_href(contact.get("telegram"))
    website_href = _normalize_external_url(contact.get("website"))
    email_href = _normalize_email_href(contact.get("email"))
    items = [*phone_items]
    if telegram_href:
        items.append({"icon": "✈", "label": "Telegram", "value": telegram_label, "href": telegram_href, "target": "_blank"})
    if website_href:
        items.append({"icon": "🌐", "label": "Сайт", "value": str(contact.get("website") or website_href).strip(), "href": website_href, "target": "_blank"})
    if email_href:
        items.append({"icon": "✉", "label": "Email", "value": str(contact.get("email") or "").strip(), "href": email_href})
    return {"phones": phone_items, "telegram_href": telegram_href, "website_href": website_href, "email_href": email_href, "contact_items": items}

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
    email = str(contacts.get("email") or "").strip()
    city = str(contacts.get("city") or "").strip()
    has_website_contacts = any([phone, *phones, telegram, viber, whatsapp, website, email])
    if has_website_contacts:
        result = {
            "has_contacts": True,
            "source": "website",
            "phone": phone,
            "phones": phones,
            "telegram": telegram,
            "viber": viber,
            "whatsapp": whatsapp,
            "website": website,
            "email": email,
            "city": city,
        }
        result["actions"] = _build_contact_actions(result)
        return result

    seller_keys = sorted(list(seller.keys())) if isinstance(seller, dict) else []
    seller_phone_candidates = [
        seller.get("phone"),
        seller.get("contact_phone"),
        seller.get("phone_number"),
        (seller.get("contacts") or {}).get("phone") if isinstance(seller.get("contacts"), dict) else None,
    ]
    seller_phone = str(next((v for v in seller_phone_candidates if str(v or "").strip()), "")).strip()
    username = str(seller.get("username") or "").strip()
    seller_telegram = str(seller.get("telegram") or (f"@{username}" if username else "")).strip()
    seller_viber = str(seller.get("viber") or "").strip()
    seller_whatsapp = str(seller.get("whatsapp") or "").strip()
    seller_website = str(seller.get("website") or "").strip()
    seller_email = str(seller.get("email") or "").strip()
    seller_city = str(seller.get("city") or "").strip()
    has_seller_contacts = any([seller_phone, seller_telegram, seller_viber, seller_whatsapp, seller_website, seller_email])
    result = {
        "has_contacts": has_seller_contacts,
        "source": "seller_profile" if has_seller_contacts else "none",
        "phone": seller_phone,
        "phones": [seller_phone] if seller_phone else [],
        "telegram": seller_telegram,
        "viber": seller_viber,
        "whatsapp": seller_whatsapp,
        "website": seller_website,
        "email": seller_email,
        "city": seller_city,
        "debug": {
            "seller_keys": seller_keys,
            "seller_phone_candidates": [str(v or "") for v in seller_phone_candidates if v is not None],
        },
    }
    result["actions"] = _build_contact_actions(result)
    logger.info(
        "website_v2 contacts detection: source=%s has_contacts=%s seller_keys=%s phone_candidates=%s resolved_phone=%s",
        result["source"],
        result["has_contacts"],
        seller_keys,
        result["debug"]["seller_phone_candidates"],
        result["phone"],
    )
    return result


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
        "current_search_query": str(seller.get("current_search_query") or ""),
        "filtered_results_count": int(seller.get("filtered_results_count") or len(raw_products) or 0),
        "search_active": bool(seller.get("search_active")),
        "current_page": int(seller.get("current_page") or 1),
        "page_size": int(seller.get("page_size") or 24),
        "total_items": int(seller.get("total_items") or len(raw_products) or 0),
        "total_pages": int(seller.get("total_pages") or 1),
        "has_next_page": bool(seller.get("has_next_page")),
        "has_prev_page": bool(seller.get("has_prev_page")),
        "next_page": seller.get("next_page"),
        "prev_page": seller.get("prev_page"),
        "active_filters": seller.get("active_filters") or {},
        "filters_active": bool(seller.get("filters_active")),
        "available_filter_options": seller.get("available_filter_options") or {"categories": [], "brands": [], "models": [], "conditions": [], "availability_options": ["available"]},
        "clear_filters_url": seller.get("clear_filters_url") or "",
        "filter_result_count": int(seller.get("filter_result_count") or 0),
        "current_sort": str(seller.get("current_sort") or "newest"),
        "sort_options": seller.get("sort_options") or ["newest", "oldest", "name_asc", "name_desc", "price_asc", "price_desc"],
        "sort_active": bool(seller.get("sort_active")),
        "sorting_label": str(seller.get("sorting_label") or "Новіші"),
        "website_contacts": website_contacts,
        "missing_required_fields": missing,
        "publish_ready": len(missing) == 0,
        "warnings": warnings,
    }


def _normalize_business_config_service(item: Any) -> dict:
    if not isinstance(item, dict):
        return {}
    title = str(item.get("title") or item.get("name") or "").strip()
    description = str(item.get("description") or item.get("text") or "").strip()
    if not (title or description):
        return {}
    try:
        sort_order = int(item.get("sort_order") or 0)
    except (TypeError, ValueError):
        sort_order = 0
    return {
        "title": title or "Послуга",
        "description": description,
        "category": str(item.get("category") or "Послуга").strip() or "Послуга",
        "price": str(item.get("price") or "").strip(),
        "image_url": str(item.get("image_url") or item.get("image") or "").strip(),
        "sort_order": sort_order,
        "cta_label": str(item.get("cta_label") or "Залишити заявку").strip() or "Залишити заявку",
    }


def build_business_website_context(website: dict, seller: dict) -> dict:
    config = get_website_v2_public_config(website)
    business_config = config.get("business") if isinstance(config.get("business"), dict) else {}
    config_services_raw = business_config.get("services") if isinstance(business_config.get("services"), list) else []
    config_services = [
        normalized
        for normalized in (_normalize_business_config_service(item) for item in config_services_raw)
        if normalized
    ]
    seller_services = seller.get("services_items") or []
    config_services = sorted(config_services, key=lambda item: int(item.get("sort_order") or 0))
    raw_services = config_services if config_services else seller_services
    services_count = len(raw_services)
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
        "available_sections": ["hero", "services", "advantages", "contact_cta", "contacts", "map", "footer"],
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
        "current_search_query": specialized.get("current_search_query", ""),
        "filtered_results_count": specialized.get("filtered_results_count", 0),
        "search_active": specialized.get("search_active", False),
        "current_page": specialized.get("current_page", 1),
        "page_size": specialized.get("page_size", 24),
        "total_items": specialized.get("total_items", 0),
        "total_pages": specialized.get("total_pages", 1),
        "has_next_page": specialized.get("has_next_page", False),
        "has_prev_page": specialized.get("has_prev_page", False),
        "next_page": specialized.get("next_page"),
        "prev_page": specialized.get("prev_page"),
        "active_filters": specialized.get("active_filters", {}),
        "filters_active": specialized.get("filters_active", False),
        "available_filter_options": specialized.get("available_filter_options", {"categories": [], "brands": [], "models": [], "conditions": [], "availability_options": ["available"]}),
        "clear_filters_url": specialized.get("clear_filters_url", ""),
        "filter_result_count": specialized.get("filter_result_count", 0),
    }
