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



def profile_conflicts(profile, values):
    from app.services.vin_resolution_policy import normalized
    actual = {"body": normalized("body_class", values.get("body_type")),
              "fuel": normalized("fuel_type", values.get("fuel_type")),
              "transmission": normalized("transmission", values.get("transmission")),
              "powertrain": {"petrol":"ICE","diesel":"ICE","HEV":"HEV","PHEV":"PHEV","BEV":"BEV"}.get(values.get("powertrain"))}
    if actual["body"] == "hatchback":
        actual["body"] = "hatch"
    return any(value is not None and profile.get(field) is not None
               and value != profile[field] for field, value in actual.items())


def managed_rows(db, vehicle, config):
    state = vehicle.dismantling_v3 or {}
    if not enabled() or not (state.get("unified_catalogue") or state.get("master_construction_intake")):
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
        if profile_conflicts(report["profile"]["profile"], config["values"]):
            raise HTTPException(409, "Характеристики суперечать джерельному каталогу")
        reference = report.get("reference_projection")
        if reference and profile_conflicts(reference["profile"], config["values"]):
            report = {**report, "reference_projection": None}
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
        if ref.get("vehicle_basis") != generator_basis(vehicle):
            return False
        identity = ref.get("identity")
        return identity is None or identity == pinned_identity(saved_state(vehicle))
    except (ValueError, KeyError, TypeError):
        return False


def auto_supplement_new_donor(db, vehicle, who):
    """Build the new donor’s construction plan in the same transaction.

    The existing create action authorizes potential plan rows only. Isolate
    optional expansion in a savepoint so unavailable sources cannot prevent
    donor creation. No update to existing source rows and no stock activation.
    """
    if not enabled() or "dismantling.manage" not in who.permissions:
        return None
    state = vehicle.dismantling_v3 or {}
    if not (state.get("unified_catalogue") or state.get("master_construction_intake")):
        return None
    if state.get("master_intake"):
        return state["master_intake"]
    from uuid import NAMESPACE_URL, uuid5
    from sqlalchemy import text
    from fastapi import HTTPException
    from app.schemas.dismantling_v3 import PlanPreview, PlanSave
    from app.services import dismantling_plan_v3 as plan
    from app.services.catalogue_import import LOCK
    from sqlalchemy.exc import SQLAlchemyError
    import logging

    outcome = {"status": "deferred", "created": 0}
    try:
        with db.begin_nested():
            if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK}):
                raise HTTPException(409, "Catalogue publication lock")
            report = plan.make_preview(db, vehicle, who, PlanPreview(facts=[], universal=True))
            if any(not any(r.get("kind") == KIND for r in p["item"]["source"])
                   for p in report["proposals"]):
                raise HTTPException(409, "Master projection unavailable")
            safe, pending = plan.partial_plan(report, plan.rows_for(db, vehicle))
            safe = {**safe, "proposals": [p for p in safe["proposals"]
                    if p["action"] == "new" and not p["target_id"] and not p["candidates"]]}
            if safe["proposals"]:
                request = PlanSave(facts=[], universal=True, confirm=True, token=report["token"],
                    request_key=uuid5(NAMESPACE_URL, "carpot.master.intake:" + vehicle.id))
                cached, sha = plan.replay(db, vehicle, who, request, "master_intake")
                result = cached if cached is not None else plan.persist_plan(
                    db, vehicle, who, request, safe, sha, partial=True, pending=pending)
                outcome = {"status": "supplemented", "created": result.get("created", 0),
                           "pending": result.get("pending", 0)}
            else:
                outcome = {"status": "no_safe_additions", "created": 0, "pending": len(pending)}
    except HTTPException as exc:
        # A source outage/conflict does not roll back creation of the donor.
        if exc.status_code not in (409, 503):
            raise
        logging.getLogger(__name__).info("Master intake deferred: %s", exc.status_code)
    except SQLAlchemyError:
        logging.getLogger(__name__).exception("Master intake savepoint rolled back")
    vehicle.dismantling_v3 = {**(vehicle.dismantling_v3 or {}), "master_intake": outcome}
    return outcome
