"""Staging-only Source-First pilot gate for a pinned modification snapshot.

Admission is based on complete observed article offers, never on brand averages,
translated names, a VIN guess or a factory-fitment claim. This module does not
modify a database, inventory, billing or Catalogue source.
"""
import os
from app.config import is_staging

MIN_PRD_TYPES = 40
MIN_PRD_OEM_PCT = 70
MIN_ARTICLE_OEM_PCT = 65
MAX_PRD_TYPES = 600
MAX_ARTICLES = 15000
ENABLED_VARIABLE = "WAREHOUSE_SOURCE_FIRST_PILOT_ENABLED"


def enabled():
    return is_staging() and os.getenv(ENABLED_VARIABLE, "").strip().lower() == "true"


def source_type(product):
    """A typed, source-linked PRD row; review types keep their exact source ID."""
    return (
        isinstance(product, dict)
        and type(product.get("product_id")) is int
        and product["product_id"] > 0
        and product.get("kind") in ("part", "consumable", "review")
        and type(product.get("article_count")) is int
        and product["article_count"] >= 0
    )


def evaluate(payload, offers_by_product):
    """Return conservative coverage decision; missing/truncated data never pass.

    Source snapshot provenance is checked in upstream CatalogueAdapter.plan.
    Every linked article is required in the per-type bounded response.
    """
    result = {
        "eligible": False,
        "reason": "invalid_snapshot",
        "source_prd_types": 0,
        "source_prd_types_with_oem": 0,
        "article_keys": 0,
        "article_keys_with_oem": 0,
        "prd_oem_pct": None,
        "article_oem_pct": None,
        "vin_fitment_verified": False,
    }
    if not isinstance(payload, dict) or not isinstance(offers_by_product, dict):
        return result
    if (type(payload.get("car_id")) is not int or payload["car_id"] <= 0
            or not isinstance(payload.get("source_snapshot_sha"), str)
            or len(payload["source_snapshot_sha"]) != 64):
        return result
    categories = payload.get("categories")
    if not isinstance(categories, list):
        return result
    valid = [p for p in categories if source_type(p)]
    if len(valid) != len([p for p in categories if isinstance(p, dict)
                        and p.get("kind") in ("part", "consumable", "review")]):
        result["reason"] = "invalid_source_type"
        return result
    if len(valid) != len({p["product_id"] for p in valid}):
        result["reason"] = "duplicate_prd"
        return result
    result["source_prd_types"] = len(valid)
    if len(valid) < MIN_PRD_TYPES:
        result["reason"] = "insufficient_prd_types"
        return result
    if len(valid) > MAX_PRD_TYPES or sum(p["article_count"] for p in valid) > MAX_ARTICLES:
        result["reason"] = "source_catalogue_exceeds_pilot_bound"
        return result

    article_keys = set()
    article_oem = set()
    types_with_oem = 0
    for product in valid:
        expected = product["article_count"]
        if expected == 0:
            continue
        rows = offers_by_product.get(product["product_id"])
        if not isinstance(rows, list) or len(rows) != expected:
            result["reason"] = "incomplete_source_articles"
            return result
        local_keys = set()
        covered = False
        for offer in rows:
            if not isinstance(offer, dict):
                result["reason"] = "invalid_article"
                return result
            sid, number = offer.get("supplier_id"), offer.get("article_nr")
            if (type(sid) is not int or not 1 <= sid <= 65535
                    or not isinstance(number, str) or not 1 <= len(number) <= 64):
                result["reason"] = "invalid_article"
                return result
            key = (sid, number)
            if key in local_keys:
                result["reason"] = "duplicate_article"
                return result
            local_keys.add(key)
            article_keys.add(key)
            numbers = offer.get("oem_numbers")
            if not isinstance(numbers, list) or any(
                not isinstance(n, str) or not 1 <= len(n.strip()) <= 150
                for n in numbers
            ):
                result["reason"] = "invalid_oem"
                return result
            if numbers and isinstance(offer.get("brand"), str) and offer["brand"].strip():
                covered = True
                article_oem.add(key)
        types_with_oem += int(covered)

    result["source_prd_types_with_oem"] = types_with_oem
    result["article_keys"] = len(article_keys)
    result["article_keys_with_oem"] = len(article_oem)
    if not article_keys:
        result["reason"] = "no_source_articles"
        return result
    result["prd_oem_pct"] = round(100 * types_with_oem / len(valid), 2)
    result["article_oem_pct"] = round(100 * len(article_oem) / len(article_keys), 2)
    if (100 * types_with_oem < MIN_PRD_OEM_PCT * len(valid)
            or 100 * len(article_oem) < MIN_ARTICLE_OEM_PCT * len(article_keys)):
        result["reason"] = "below_pilot_oem_coverage"
        return result
    result["reason"] = "source_first_qualified"
    result["eligible"] = True
    return result
