"""Stage 8 read-only Warehouse OEM PRD mapping gap audit.

Finds source-identity/mapping gaps for Volvo XC90 donors in isolated staging.
No stock or plan mutations, no VIN output, no automatic string-based mapping.
Source category suggestions are ONLY review candidates, not OEM fitment.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import os

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.config import database_url, is_staging
from app.models import Vehicle, DismantlingItem
from app.services import unified_catalogue as catalogue
from app.services.auto_oem import (
    SourceCache, canonical_prd_bindings, eligible_row, matches,
    source_identity, references, valid_reference, oracle_enabled,
)
from app.services.volvo_oem_review import candidates

MAX_DONORS = 3
MAX_ROWS = 250
MAX_GAPS = 200


def explain(row, products, bindings, car_id):
    """Small, bounded read-only explanation of source binding state."""
    pid = catalogue.row_product_id(row)
    if pid is not None:
        if getattr(row, "source", None) == "carpot.catalogue.v1":
            if getattr(row, "catalog_key", None) != f"car:{car_id}:product:{pid}":
                return "stale_modification_prd_key"
        p = products.get(pid)
        if p is None:
            return "prd_id_missing_from_selected_source"
        if not p.get("article_count"):
            return "source_prd_without_linked_articles"
        return "source_prd_type_not_verified"
    canonical_id = (getattr(row, "plan_v3", None) or {}).get("canonical_part_type_id")
    if canonical_id is not None:
        proof = bindings.get(canonical_id)
        if not proof:
            return "canonical_without_source_prd_proof"
        return "canonical_prd_not_uniquely_matched"
    return "no_verified_source_prd_binding"


def summarize(rows, products, bindings, source_car_id, refs, vehicle):
    counted = Counter()
    gaps = []
    list_products = list(products.values())
    for row in rows:
        if not eligible_row(row):
            continue
        selected = matches(row, products, bindings,
                           source_modification_id=source_car_id)
        ref = refs.get(row.id)
        counted["included_rows"] += 1
        if valid_reference(vehicle, row, ref):
            counted["valid_saved_refs"] += 1
        if selected is not None:
            counted["mapped_source_prd"] += 1
            if selected.get("article_count"):
                counted["mapped_with_article_candidates"] += 1
            continue
        reason = explain(row, products, bindings, source_car_id)
        counted["unmatched_source_prd"] += 1
        counted[reason] += 1
        if len(gaps) < MAX_GAPS:
            hints = candidates(row, list_products)
            gaps.append({
                "part_name": (row.name or "")[:160],
                "category": (row.category_name or "")[:100],
                "subcategory": (row.subcategory_name or "")[:100],
                "source": str(row.source or "")[:60],
                "reason": reason,
                "review_only_product_ids": hints[:8],
                "not_fitment_verified": True,
            })
    for key in ("mapped_source_prd", "mapped_with_article_candidates",
                "unmatched_source_prd", "valid_saved_refs"):
        counted.setdefault(key, 0)
    return {
        "counts": dict(counted),
        "unmatched_examples": gaps,
        "examples_truncated": counted["unmatched_source_prd"] > len(gaps),
    }


def audit():
    if not is_staging() or os.getenv("RAILWAY_ENVIRONMENT_NAME") != "warehouse-staging":
        raise RuntimeError("STOP: warehouse-staging only")
    engine = create_engine(database_url(), poolclass=NullPool)
    output = {"stage": "8_warehouse_prd_mapping", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "read_only": True, "fitment_verified": False,
              "oracle_fallback_enabled": oracle_enabled(),
              "target": "Volvo XC90 year 2016; up to 3 donors",
              "donors": [], "skipped": []}
    cache = SourceCache()
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            vehicles = list(db.scalars(
                select(Vehicle).where(
                    Vehicle.archived.is_(False),
                    Vehicle.manufacturer.ilike("volvo"),
                    Vehicle.model.ilike("%xc90%"),
                    Vehicle.year == 2016,
                ).order_by(Vehicle.id).limit(60)
            ))
            candidates_by_donor = []
            for v in vehicles:
                identity = source_identity(v)
                if identity is not None and identity[0] == 107555:
                    candidates_by_donor.append((v, identity))
            # First inspect donors with large existing plans; representative
            # legacy PRD gaps are otherwise hidden by empty vehicles.
            for v, identity in candidates_by_donor[:60]:
                rows = list(db.scalars(select(DismantlingItem).where(
                    DismantlingItem.vehicle_id == v.id,
                    DismantlingItem.account_id == v.account_id,
                ).limit(MAX_ROWS + 1)))
                if len(rows) > MAX_ROWS:
                    output["skipped"].append({"reason": "donor_plan_exceeds_bounded_cap"})
                    continue
                if not rows:
                    continue
                output["donors"].append((v, identity, rows))
            output["donors"].sort(key=lambda item: -len(item[2]))
            output["donors"] = output["donors"][:MAX_DONORS]
            completed = []
            for v, identity, rows in output["donors"]:
                bindings = canonical_prd_bindings(db, rows)
                try:
                    payload = cache.plan(identity)
                except Exception as exc:
                    completed.append({"donor_number": str(v.number or "")[:30],
                                      "rows": len(rows), "status": "source_plan_unavailable",
                                      "error_class": type(exc).__name__})
                    continue
                products = {p["product_id"]: p for p in payload["categories"]}
                summary = summarize(rows, products, bindings, identity[0],
                                    references(v), v)
                completed.append({
                    "donor_number": str(v.number or "")[:30],
                    "model": str(v.model or "")[:60],
                    "source_modification_id": identity[0],
                    "source_category_count": len(products),
                    "source_snapshot_sha": payload["source_snapshot_sha"],
                    "plan_rows": len(rows),
                    "status": "ok", **summary,
                })
            output["donors"] = completed
            db.rollback()
    finally:
        engine.dispose()
    return output


if __name__ == "__main__":
    print("STAGE8_WAREHOUSE_BINDING_START", flush=True)
    print(json.dumps(audit(), ensure_ascii=True, indent=2), flush=True)
    print("STAGE8_WAREHOUSE_BINDING_END", flush=True)
