"""Reconcile Master construction with optional exact Warehouse source data.

The compact Oracle graph deliberately carries no installation attributes. It can
prove source article associations, not the side, axle or ordinal of a new item.
Never fabricate physical rows or transfer OEM from sibling modifications.
"""
from collections import Counter
from pathlib import Path
from copy import deepcopy
import json
import re

from app.services.catalogue_format import digest
from app.services.master_parts_preview import preview, read_seed

SEED = Path(__file__).resolve().parents[1] / "data" / "master_parts_seed_v02.tsv"
VERSION = "carpot.master.parts.reconciliation.v1"
REFERENCE_PROFILES = SEED.with_name('master_parts_reference_profiles.json')


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



def reference_profile(identity, year, base, *, records=None):
    """Model-year reference, separate from actual vehicle facts and fitment.

    A missing exact key or any disagreement with known source facts disables
    reference expansion. No reference values are used for OEM assignment.
    """
    records = json.loads(REFERENCE_PROFILES.read_text(encoding="utf-8")) if records is None else records
    key = {k: identity.get(k) for k in ("kind", "manufacturer_id", "model_id", "car_id")}
    matches = [r for r in records if r.get("identity") == key and r.get("year") == year]
    if len(matches) != 1 or not matches[0].get("sources"):
        return None
    record = matches[0]

    def merge(a, b):
        if a is None:
            return deepcopy(b)
        if isinstance(a, dict) and isinstance(b, dict):
            return {k: merge(a.get(k), b[k]) if k in b else deepcopy(a[k])
                    for k in a.keys() | b.keys()}
        if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            return [merge(x, y) for x, y in zip(a, b)]
        if a == b:
            return deepcopy(a)
        raise ValueError("conflicting reference facts")

    try:
        result = merge(base, record["profile"])
    except ValueError:
        return None
    return {"profile": result, "reference_id": record["id"], "sources": record["sources"],
            "scope": record["scope"], "physical_fitment_verified": False}



def reported_topology(base, details):
    """Use explicit reviewed VIN observations as candidate geometry, not fitment.

    Door counts for regular passenger bodies map to side-door positions. The
    interpretation is not extended to vans, pickups, buses or commercial cabs.
    Unknown or conflicting observations never override the Oracle profile.
    """
    from app.services.vin_resolution_policy import normalized
    if (details or {}).get("trust") != "server_vin_report_with_operator_review":
        return deepcopy(base)
    conflicted = set(details.get("conflicts") or {}) | set(details.get("consistency_issues") or {})
    facts = {key: value for key, value in (details.get("characteristics") or {}).items()
             if key not in conflicted}
    p = deepcopy(base)
    body = normalized("body_class", facts.get("body_class"))
    body = {"hatchback": "hatch"}.get(body, body)
    if p.get("kind") == "passenger" and body in {"sedan", "coupe", "hatch", "wagon", "suv", "convertible"}:
        if p.get("body") not in (None, body):
            return p
        p["body"] = body
        doors = normalized("doors", facts.get("doors"))
        side_count = {2: 2, 3: 2, 4: 4, 5: 4}.get(doors)
        if (side_count and (body not in {"sedan", "coupe", "convertible"} or doors in (2, 4))
                and (body != "coupe" or side_count == 2)):
            positions = ["FL", "FR"] + (["RL", "RR"] if side_count == 4 else [])
            if p.get("side_doors") in (None, positions):
                p["side_doors"] = positions
    cylinders = normalized("engine_cylinders", facts.get("engine_cylinders"))
    if type(cylinders) is int and 1 <= cylinders <= 32:
        counts = p.setdefault("counts", {})
        if counts.get("cylinders") in (None, cylinders):
            counts["cylinders"] = cylinders
    return p


def construction_reference(vehicle, *, source_model_id=None):
    """A reviewed model-year profile is usable without a parts identity."""
    from app.services.vin_resolution_policy import key
    records = json.loads(REFERENCE_PROFILES.read_text(encoding="utf-8"))
    matches = [r for r in records if r.get("family")
               and r["family"]["manufacturer"] == key(vehicle.manufacturer)
               and key(vehicle.model) in {key(name) for name in r["family"]["models"]}
               and r["year"] == vehicle.year and r["sources"]
               and (source_model_id is None or r["family"]["oracle_model_id"] == source_model_id)]
    if len(matches) == 1 and getattr(vehicle, "generation", ""):
        generation = key(vehicle.generation)
        matches = [r for r in matches if generation in {key(name) for name in r["family"]["generations"]}]
    return matches[0] if len(matches) == 1 else None


def construction_profile(vehicle, base, hint):
    from app.services.vin_resolution_policy import normalized

    profile = deepcopy(base)
    fuel = normalized("fuel_type", getattr(vehicle, "fuel_type", None))
    if fuel in ("petrol", "diesel"):
        profile.setdefault("fuel", fuel)
        profile.setdefault("flags", {}).setdefault("ice", True)
    details = getattr(vehicle, "vin_details", None) or {}
    trusted = details.get("trust") == "server_vin_report_with_operator_review"
    vehicle_type = str((details.get("characteristics") or {}).get("vehicle_type") or "").casefold() if trusted else ""
    if not profile.get("kind"):
        profile["kind"] = hint.get("kind") or (
            "heavy_truck" if "тягач" in vehicle_type else
            "passenger" if any(v in vehicle_type for v in ("легков", "пасажир", "passenger", "mpv")) else None)
    if not profile.get("body") and hint.get("body"):
        profile["body"] = hint["body"]
    if not profile.get("side_doors") and hint.get("side_doors"):
        profile["side_doors"] = ["FL", "FR"] + (["RL", "RR"] if hint["side_doors"] == 4 else [])
    profile = reported_topology(profile, details)
    if profile["kind"] is None and profile.get("body") in {"sedan", "hatch", "wagon", "suv", "coupe", "convertible"}:
        profile["kind"] = "passenger"
    # This path is only for identified motor vehicles. Unknown class still
    # permits common components while class-/axle-specific positions wait.
    profile.setdefault("flags", {}).setdefault("all", True)
    positions = profile.setdefault("positions", {})
    for name in ("headlamp", "taillamp"):
        positions.setdefault(name, ["L", "R"])
    if profile["kind"] == "passenger":
        positions.setdefault("mirror", ["L", "R"])
        positions.setdefault("bumper", ["front", "rear"])
    elif profile.get("body") == "tractor":
        positions.setdefault("cab_mirror", ["L", "R"])
        positions.setdefault("cab_door", ["L", "R"])
    return profile


def preview_for_vehicle(db, vehicle, *, adapter=None):
    """Build physical candidates and preserve every exact, validated source row."""
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models import DismantlingItem
    from app.services import unified_catalogue, vin_source_directory
    from app.services.dismantling_plan_v3 import generator_basis
    from app.services.master_parts_oracle_profile import oracle_profile
    from app.services.master_parts_managed import master_ref

    state = vehicle.dismantling_v3 or {}
    basis = generator_basis(vehicle)
    saved = unified_catalogue.saved_state(vehicle)
    if unified_catalogue.needs_review(vehicle):
        return {"status": "missing_or_stale_source_plan", "persisted": False}
    locator = state.get("oracle_vehicle_identity") or {}
    identity = None
    normalized = {"profile": {}, "source_facts": {}, "missing": [], "conflicts": [], "fitment_verified": False}
    if saved:
        try:
            identity = pinned_identity(saved)
        except (ValueError, KeyError, TypeError):
            return {"status": "invalid_source_plan", "persisted": False}
        if (locator.get("source") != "oracle" or locator.get("identity_fingerprint") != basis
                or (locator.get("kind"), locator.get("manufacturer_id"), locator.get("model_id"),
                    locator.get("source_modification_id")) !=
                   (identity["kind"], identity["manufacturer_id"], identity["model_id"], identity["car_id"])):
            return {"status": "unverified_vehicle_identity", "persisted": False}

    if locator.get("source") == "oracle" and locator.get("identity_fingerprint") == basis:
        kind, car_id = locator["kind"], locator["source_modification_id"]
        if kind == "passenger":
            normalized["profile"]["kind"] = "passenger"
        try:
            attributes = locator.get("source_attributes")
            if attributes:
                response = dict(source="oracle", kind=kind, source_modification_id=car_id,
                                truncated=False, vehicle_identity_only=True,
                                fitment_verified=False, items=attributes)
            else:
                response = vin_source_directory.fetch(adapter or unified_catalogue.CatalogueAdapter(), "attributes",
                    {"kind": kind, "car_id": car_id, "limit": 50}, kind)
            normalized = oracle_profile(response, expected_kind=kind, expected_car_id=car_id)
        except (HTTPException, ValueError):
            normalized["missing"].append("oracle_attributes")
    hint = state.get("master_construction_intake") or {}
    hint = hint.get("facts", {}) if hint.get("vehicle_basis") == basis else {}
    if not hint and not locator and not saved and not state.get("master_construction_intake"):
        return {"status": "missing_or_stale_source_plan", "persisted": False}
    reference = construction_reference(vehicle, source_model_id=locator.get("model_id") or hint.get("model_id"))
    if reference:
        hint = {**hint, "kind": reference["profile"]["kind"]}
    normalized["profile"] = construction_profile(vehicle, normalized["profile"], hint)

    rows = list(db.scalars(select(DismantlingItem).where(
        DismantlingItem.account_id == vehicle.account_id, DismantlingItem.vehicle_id == vehicle.id)))
    existing = []
    for row in rows:
        item = {"product_id": unified_catalogue.row_product_id(row),
                "row_id": row.id, "protected": bool(row.part_id or row.received_at)}
        ref = master_ref(row)
        if ref and ref.get("vehicle_basis") == basis and ref.get("identity") in (None, identity):
            item.update(master_key=ref.get("master_key"), placement=ref.get("master_placement"))
        existing.append(item)

    def generate(profile):
        if saved:
            return reconcile(saved, profile, existing_rows=existing)
        candidate = preview(read_seed(SEED), profile, existing_rows=existing)
        return {**candidate, "version": VERSION, "identity": None,
                "source_type_count": 0, "source_types_with_oem": 0, "source_rows_retained": 0,
                "physical_candidate_count": len(candidate["positions"]),
                "gap_candidate_count": candidate["counts"].get("supplement_candidate", 0),
                "reconciliation_count": candidate["counts"].get("reconcile", 0),
                "source_cross_reference_candidate_count": 0,
                "automatically_assigned_physical_oem": 0, "persisted": False,
                "stock_changed": False, "fitment_verified": False}

    report = generate(normalized["profile"])
    if reference:
        match_key = {k: (identity or {}).get(k) for k in ("kind", "manufacturer_id", "model_id", "car_id")}
        reference = reference_profile(match_key, vehicle.year, normalized["profile"],
                                      records=[{**reference, "identity": match_key}])
    elif identity:
        reference = reference_profile(identity, vehicle.year, normalized["profile"])
    projection = None
    if reference:
        candidate = generate(reference["profile"])
        for item in candidate["positions"]:
            item["source_article_candidates"] = []
            item["oem_status"] = "reference_topology_only"
        projection = {**reference, **candidate, "source_cross_reference_candidate_count": 0, "reference_only": True}
    return {**report, "status": "preview", "profile": normalized, "reference_projection": projection,
            "existing_plan_row_count": len(rows),
            "protected_row_count": sum(r["protected"] for r in existing)}
