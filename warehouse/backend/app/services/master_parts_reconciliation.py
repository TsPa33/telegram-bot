"""Read-only integration of Master Catalogue with a pinned Warehouse source plan.

The compact Oracle graph deliberately carries no installation attributes. It can
prove source article associations, not the side, axle or ordinal of a new item.
Never fabricate physical rows or transfer OEM from sibling modifications.
"""
from collections import Counter
from pathlib import Path
import re

from app.services.catalogue_format import digest
from app.services.master_parts_preview import preview, read_seed

SEED = Path(__file__).resolve().parents[1] / "data" / "master_parts_seed_v02.tsv"
VERSION = "carpot.master.parts.reconciliation.v1"


def pinned_identity(saved):
    payload = saved["payload"]
    if digest(payload) != saved.get("sha256"):
        raise ValueError("saved plan checksum mismatch")
    identity = {k: payload.get(k) for k in ("kind", "manufacturer_id", "model_id", "car_id")}
    identity["snapshot_sha"] = payload.get("source_snapshot_sha")
    if (identity["kind"] not in ("passenger", "commercial")
            or any(type(identity[k]) is not int or identity[k] <= 0
                   for k in ("manufacturer_id", "model_id", "car_id"))
            or not re.fullmatch(r"[0-9a-f]{64}", identity["snapshot_sha"] or "")):
        raise ValueError("incomplete pinned identity")
    return identity


def linked_offers(saved):
    """Strictly validate the existing compact graph and every product link."""
    payload = saved["payload"]
    graph = saved.get("article_graph")
    if graph is None:
        return {}
    if digest(graph) != payload.get("article_graph_sha"):
        raise ValueError("article graph checksum mismatch")
    items, links = graph["items"], graph["product_links"]
    if not isinstance(items, list) or not isinstance(links, dict):
        raise ValueError("invalid article graph")
    products = {r["product_id"]: r for r in payload["categories"]}
    if not set(links) <= {str(k) for k in products}:
        raise ValueError("foreign product link")
    offers = []
    keys = set()
    for item in items:
        if not isinstance(item, list) or len(item) != 4:
            raise ValueError("invalid article tuple")
        sid, number, brand, codes = item
        if (type(sid) is not int or sid <= 0 or not isinstance(number, str)
                or not number.strip() or not isinstance(brand, str)
                or not isinstance(codes, list)
                or any(not isinstance(c, str) or not c.strip() or len(c) > 150 for c in codes)):
            raise ValueError("invalid supplier article")
        if (sid, number) in keys:
            raise ValueError("duplicate supplier article")
        keys.add((sid, number))
        offers.append({"supplier_id": sid, "article_number": number,
                       "brand": brand, "oem_numbers": sorted(set(codes))})
    result = {}
    for pid, product in products.items():
        indexes = links.get(str(pid), [])
        if (not isinstance(indexes, list)
                or any(type(i) is not int or not 0 <= i < len(offers) for i in indexes)
                or len(set(indexes)) != len(indexes)
                or len(indexes) != product.get("article_count")):
            raise ValueError("incomplete product article links")
        result[pid] = [offers[i] for i in indexes]
    return result


def physical_key(master_key, placement):
    return "master:" + digest([master_key, placement])[:48]


def reconcile(saved, profile, *, existing_rows=(), seed=None):
    """Construct a non-destructive projection, never a persisted receipt plan."""
    identity = pinned_identity(saved)
    products = saved["payload"]["categories"]
    offers = linked_offers(saved)
    seed = read_seed(SEED) if seed is None else seed
    report = preview(seed, profile, products, existing_rows, identity=identity)
    by_type = Counter(r["master_key"] for r in report["positions"])
    reviews = {r["master_key"] for r in report["review"]}
    by_product = {p['product_id']: p for p in products}
    proposed = []
    for row in report["positions"]:
        item = dict(row, physical_key=physical_key(row["master_key"], row["placement"]))
        item["source_article_candidates"] = []
        # A uniquely applicable single unit can expose exact-source references
        # as candidates. It does not turn them into installed physical OEM.
        if (row["placement"] == "unit:1" and by_type[row["master_key"]] == 1
                and row["master_key"] not in reviews and len(row["source_ids"]) == 1):
            pid = row["source_ids"][0]
            product = by_product[pid]
            if product.get("kind") == "part" and product.get("source_fitment_linked") is True:
                item["source_article_candidates"] = [
                    dict(a, product_id=pid, evidence="exact_source_article_cross_reference",
                         physical_fitment_verified=False)
                    for a in offers.get(pid, []) if a["brand"] and a["oem_numbers"]
                ]
        item["oem_status"] = ("source_cross_reference_only" if item["source_article_candidates"]
                              else "placement_evidence_missing" if row["source_ids"]
                              else "source_prd_link_missing")
        proposed.append(item)
    counts = Counter(r["state"] for r in proposed)
    return {"version": VERSION, "identity": identity,
            "source_type_count": len(products),
            "source_types_with_oem": sum(any(a["oem_numbers"] for a in v) for v in offers.values()),
            "physical_candidate_count": len(proposed),
            "gap_candidate_count": counts["supplement_candidate"],
            "reconciliation_count": counts["reconcile"],
            "source_cross_reference_candidate_count": sum(bool(r["source_article_candidates"]) for r in proposed),
            "automatically_assigned_physical_oem": 0,
            "positions": proposed, "review": report["review"],
            "excluded": report["excluded"], "unmapped_source_ids": report["unmapped_source_ids"],
            "source_rows_retained": len(products),
            "persisted": False, "stock_changed": False, "fitment_verified": False}


def preview_for_vehicle(db, vehicle, *, adapter=None):
    """Use the real saved plan and current exact Oracle identity; read-only."""
    from sqlalchemy import select
    from app.models import DismantlingItem
    from app.services import unified_catalogue, vin_source_directory
    from app.services.dismantling_plan_v3 import generator_basis
    from app.services.master_parts_oracle_profile import oracle_profile

    saved = unified_catalogue.saved_state(vehicle)
    if not saved or unified_catalogue.needs_review(vehicle):
        return {"status": "missing_or_stale_source_plan", "persisted": False}
    try:
        identity = pinned_identity(saved)
    except (ValueError, KeyError, TypeError):
        return {"status": "invalid_source_plan", "persisted": False}
    locator = (vehicle.dismantling_v3 or {}).get("oracle_vehicle_identity", {})
    if (locator.get("source") != "oracle"
            or locator.get("identity_fingerprint") != generator_basis(vehicle)
            or (locator.get("kind"), locator.get("manufacturer_id"),
                locator.get("model_id"), locator.get("source_modification_id")) !=
               (identity["kind"], identity["manufacturer_id"], identity["model_id"], identity["car_id"])):
        return {"status": "unverified_vehicle_identity", "persisted": False}
    response = vin_source_directory.fetch(
        adapter or unified_catalogue.CatalogueAdapter(), "attributes",
        {"kind": identity["kind"], "car_id": identity["car_id"], "limit": 50},
        identity["kind"])
    normalized = oracle_profile(response, expected_kind=identity["kind"],
                                expected_car_id=identity["car_id"])
    rows = list(db.scalars(select(DismantlingItem).where(
        DismantlingItem.account_id == vehicle.account_id,
        DismantlingItem.vehicle_id == vehicle.id)))
    existing = [{"product_id": unified_catalogue.row_product_id(r),
                 "row_id": r.id, "protected": bool(r.part_id or r.received_at)}
                for r in rows]
    report = reconcile(saved, normalized["profile"], existing_rows=existing)
    return {**report, "status": "preview", "profile": normalized,
            "existing_plan_row_count": len(rows),
            "protected_row_count": sum(r["protected"] for r in existing)}
