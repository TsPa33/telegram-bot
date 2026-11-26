"""Staging-only bridge from a Master reconciliation to the existing managed v3 plan.

No Part/Operation creation, no new persistence path, no inferred OEM links.
Only gap candidates are offered; mapped PRD rows are retained as-is.
"""
import os
from app.config import is_staging
from app.services.canonical_rules import sid, placement
from app.services.master_parts_reconciliation import physical_key

KIND = "master_construction"


def enabled():
    return is_staging() and os.getenv("WAREHOUSE_MASTER_PARTS_ENABLED", "false").lower() == "true"


def master_ref(row):
    refs = (getattr(row, "plan_v3", None) or {}).get("snapshot", {}).get("source", [])
    matches = [r for r in refs if r.get("kind") == KIND]
    return matches[0] if len(matches) == 1 else None


def installation(raw):
    tokens = raw.split(":")
    side = "unknown"
    pos = "unknown"
    if tokens[0] == "door" and len(tokens) >= 2:
        side = {"FL":"left","FR":"right","RL":"left","RR":"right","SL":"left","SR":"right"}.get(tokens[1], "unknown")
        pos = {"FL":"front","FR":"front","RL":"rear","RR":"rear"}.get(tokens[1], "unknown")
    elif tokens[0] in ("front", "rear"):
        pos = tokens[0]
    if "L" in tokens:
        side = "left"
    elif "R" in tokens:
        side = "right"
    return dict(side=side, position=pos, mount=[], ordinal=[raw])


def label(raw):
    tokens = raw.split(":")
    if tokens[0] == "unit":
        return "№ " + tokens[-1] if tokens[-1] != "1" else ""
    if tokens[0] == "axle":
        text = "Вісь " + tokens[1]
        if len(tokens) > 2:
            text += {"L":" · ліва","R":" · права"}.get(tokens[2], "")
        if len(tokens) > 3:
            text += " · № " + tokens[-1]
        return text
    if tokens[0] == "door":
        text = {"FL":"передні ліві","FR":"передні праві","RL":"задні ліві","RR":"задні праві","SL":"бокові ліві","SR":"бокові праві"}.get(tokens[1], tokens[1])
        return text + (" · № " + tokens[-1] if len(tokens) > 2 else "")
    return {"L":"ліва","R":"права","front":"передня","rear":"задня","rear:lid":"задня кришка","rear:liftgate":"двері багажника","rear:tailgate":"задній борт","rear:door:L":"задні ліві","rear:door:R":"задні праві"}.get(raw, raw)


def candidate_rows(report, *, basis):
    """Translate only non-overlapping proposals, retaining deterministic identities."""
    selected = report.get("reference_projection") or report
    result = []
    for row in selected.get("positions", []):
        if row["state"] not in ("supplement_candidate", "existing") or row["source_ids"]:
            continue
        key = row["master_key"]
        raw = row["placement"]
        tid = sid("master-construction-type", key)
        p = placement(dict(type_id=tid, installation=installation(raw)))
        path = row["category_path"]
        ref = dict(kind=KIND, key=physical_key(key, raw), master_key=key, master_placement=raw,
                   identity=report["identity"], vehicle_basis=basis,
                   reference_id=selected.get("reference_id"), position_label=label(raw))
        result.append(dict(canonical_type_id=tid, name=row["name_uk"], category=path[0], subcategory=path[1],
            placement=p, variants=[], source_refs=[ref], source_ref_count=1, offer_count=0,
            source_confirmed=False, applicability=dict(groups=["E"], required_fields=[],
            missing_or_unverified=["physical_inspection"], conflicting_fields=[])))
    return result


def managed_rows(db, vehicle, config):
    if not enabled() or not (vehicle.dismantling_v3 or {}).get("unified_catalogue"):
        return None
    from app.services.master_parts_reconciliation import preview_for_vehicle
    from app.services.dismantling_plan_v3 import generator_basis
    from fastapi import HTTPException
    if config.get("conflicts"):
        raise HTTPException(409, "Характеристики суперечливі; наявний план збережено")
    if (vehicle.dismantling_v3 or {}).get("inventory_mode") == "virtual_v1":
        raise HTTPException(409, "Доповнення Master для віртуального обліку ще не підтримується")
    try:
        report = preview_for_vehicle(db, vehicle)
        if report.get("status") != "preview":
            raise HTTPException(409, "Потрібна звірка джерельного каталогу перед доповненням")
        return candidate_rows(report, basis=generator_basis(vehicle))
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, "Не вдалося перевірити конструктивний каталог; план збережено") from None


def receipt_allowed(vehicle, row, quantity):
    ref = master_ref(row)
    if ref is None:
        return True
    from app.services.dismantling_plan_v3 import generator_basis
    from app.services.master_parts_reconciliation import pinned_identity
    from app.services.unified_catalogue import saved_state, needs_review
    if quantity != 1 or vehicle is None or needs_review(vehicle):
        return False
    try:
        return (ref.get("vehicle_basis") == generator_basis(vehicle)
                and ref.get("identity") == pinned_identity(saved_state(vehicle)))
    except (ValueError, KeyError, TypeError):
        return False
