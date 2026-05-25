import copy

SITE_TYPE_CATALOG = "carpot_catalog"
SITE_TYPE_BUSINESS = "carpot_business"
ALLOWED_SITE_TYPES = {SITE_TYPE_CATALOG, SITE_TYPE_BUSINESS}


def normalize_website_v2_type(site_type: str | None) -> str:
    value = str(site_type or "").strip().lower()
    if value in {"catalog", "shop", SITE_TYPE_CATALOG}:
        return SITE_TYPE_CATALOG
    if value in {"business", "service", SITE_TYPE_BUSINESS}:
        return SITE_TYPE_BUSINESS
    raise ValueError("Invalid website type")


def default_website_v2_config(site_type: str) -> dict:
    normalized = normalize_website_v2_type(site_type)
    is_catalog = normalized == SITE_TYPE_CATALOG
    return {
        "website_v2": {
            "version": 1,
            "site_type": normalized,
            "design": {"style": "carpot_brutal_bw", "template": "default"},
            "hero": {"title": "", "subtitle": "", "primary_cta": "", "secondary_cta": "", "banner_url": ""},
            "catalog": {"enabled": is_catalog, "title": "", "description": ""},
            "business": {"enabled": not is_catalog, "title": "", "description": ""},
            "contacts": {},
            "map": {},
            "seo": {},
            "publication": {},
        }
    }


def _deep_merge(base: dict, patch: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_website_v2_defaults(config: dict | None, site_type: str) -> dict:
    defaults = default_website_v2_config(site_type)
    incoming = config if isinstance(config, dict) else {}
    merged = _deep_merge(defaults, incoming)
    merged["website_v2"]["site_type"] = normalize_website_v2_type(site_type)
    return merged


def patch_website_v2_config(config: dict | None, patch: dict | None) -> dict:
    current = config if isinstance(config, dict) else {}
    incoming = patch if isinstance(patch, dict) else {}
    site_type = ((current.get("website_v2") or {}).get("site_type")) or SITE_TYPE_CATALOG
    merged = merge_website_v2_defaults(current, site_type)
    return _deep_merge(merged, incoming)
