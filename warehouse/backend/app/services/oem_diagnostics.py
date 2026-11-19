"""Read-only audit of OEM auto-assignment blockers for known control vehicles.

No catalogue/provider requests, no part updates, no cross-tenant actor data.
"""
from collections import Counter
from sqlalchemy import select
from app.models import Vehicle, DismantlingItem, Part
from app.services import auto_oem
from app.services import unified_catalogue as catalogue

CONTROL_VINS = {
    "XLRTE47MS0E774889": "DAF XF",
    "YV4A22PK2G1092943": "Volvo XC90",
    "YV4L12RK6N1970668": "Volvo XC60",
}


def audit(db):
    report = []
    for vin,label in CONTROL_VINS.items():
        vehicles = db.scalars(select(Vehicle).where(
            Vehicle.vin==vin, Vehicle.archived.is_(False)
        ).limit(100)).all()
        grouped = Counter()
        reasons = Counter()
        for car in vehicles:
            state = car.dismantling_v3 or {}
            refs = auto_oem.references(car) or {}
            identity = auto_oem.source_identity(car)
            entries = db.scalars(select(DismantlingItem).where(
                DismantlingItem.vehicle_id==car.id,
                DismantlingItem.account_id==car.account_id)).all()
            parts = db.scalars(select(Part).where(
                Part.vehicle_id==car.id,Part.account_id==car.account_id,
                Part.archived.is_(False))).all()
            grouped['vehicles'] += 1
            grouped['dismantling_rows'] += len(entries)
            grouped['included_rows'] += sum(1 for r in entries if auto_oem.eligible_row(r))
            grouped['stored_oem_refs'] += sum(1 for value in refs.values()
                                              if isinstance(value,dict) and value.get('oem_number'))
            grouped['eligible_rows_without_oem_ref'] += sum(
                1 for r in entries if auto_oem.eligible_row(r)
                and not (isinstance(refs.get(r.id), dict) and refs[r.id].get('oem_number'))
            )
            grouped['valid_oem_refs'] += sum(
                1 for r in entries if auto_oem.eligible_row(r)
                and isinstance(refs.get(r.id), dict)
                and auto_oem.valid_reference(car, r, refs[r.id])
            )
            grouped['stock_parts'] += len(parts)
            grouped['stock_with_oem'] += sum(bool(p.oem_number) for p in parts)
            grouped['stock_manual_oem_clear'] += sum(
                bool(p.oem_provenance and not p.oem_number) for p in parts
            )
            linked = {r.part_id: r for r in entries if r.part_id is not None}
            grouped['stock_linked_to_dismantling_row'] += sum(p.id in linked for p in parts)
            grouped['stock_linked_valid_oem_ref_without_oem'] += sum(
                1 for p in parts
                if not p.oem_number and p.id in linked
                and isinstance(refs.get(linked[p.id].id), dict)
                and auto_oem.valid_reference(car, linked[p.id], refs[linked[p.id].id])
                and not p.oem_provenance
            )
            grouped['stock_with_article'] += sum(bool(p.article_number and p.article_brand) for p in parts)
            grouped['stock_with_exact_supplier'] += sum(bool(auto_oem.exact_key(p,car)) for p in parts)
            if identity:
                grouped['vehicles_with_source_identity'] += 1
                if identity[0] == 107555:
                    reasons['matched_reviewed_xc90_107555'] += 1
                else:
                    reasons['has_pinned_catalogue_identity'] += 1
            elif state.get('global_selection') or catalogue.saved_state(car):
                reasons['stale_or_incomplete_catalogue_selection'] += 1
            elif not car.engine_code:
                reasons['missing_exact_engine_code_and_modification'] += 1
            elif car.year is None:
                reasons['missing_model_year'] += 1
            else:
                reasons['needs_unique_directory_modification_match'] += 1
            if not entries and not parts:
                reasons['no_dismantling_rows_or_stock'] += 1
            if parts and not any(p.article_number and p.article_brand for p in parts):
                reasons['stock_has_no_exact_supplier_article'] += 1
            if any(p.oem_provenance and not p.oem_number for p in parts):
                reasons['stock_manual_oem_clear_protected'] += 1
        report.append({
            "model": label,
            "vin": vin,
            "counts": dict(grouped),
            "reasons": dict(reasons),
            "classification": "read_only_diagnostic_not_fitment",
        })
    return {"status": "reported", "read_only": True,
            "external_requests": 0, "provider_credits": 0,
            "vehicles": report}
