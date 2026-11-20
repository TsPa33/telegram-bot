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


def _percent(numerator, denominator):
    return round(100 * numerator / denominator, 2) if denominator else None


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
            automatic = auto_oem.automatic_identity(car)
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
                and auto_oem.transferable_reference(refs.get(r.id))
                and auto_oem.valid_reference(car, r, refs[r.id])
            )
            grouped['selected_modification_oems'] += sum(
                1 for row in entries if auto_oem.eligible_row(row) and auto_oem.valid_reference(car,row,refs.get(row.id))
                and refs[row.id].get('status')==auto_oem.AUTO_STATUS
            )
            grouped['manually_selected_plan_oems'] += sum(
                1 for row in entries if auto_oem.eligible_row(row) and auto_oem.valid_reference(car,row,refs.get(row.id))
                and refs[row.id].get('status')=='user_selected_cross_reference'
            )
            other=state.get(auto_oem.CANDIDATES_KEY) or {}
            grouped['positions_with_unconfirmed_other_modification_oems'] += sum(
                bool(other.get(row.id)) for row in entries if auto_oem.eligible_row(row)
            )
            outcomes=state.get(auto_oem.OUTCOMES_KEY) or {}
            for row in entries:
                if auto_oem.eligible_row(row) and outcomes.get(row.id):
                    grouped[outcomes[row.id]]+=1
            grouped['stock_parts'] += len(parts)
            current_stock = [p for p in parts if p.quantity > 0 and p.availability != 'absent']
            grouped['eligible_stock_parts'] += len(current_stock)
            grouped['eligible_stock_with_oem'] += sum(bool(p.oem_number) for p in current_stock)
            grouped['stock_with_oem'] += sum(bool(p.oem_number) for p in parts)
            grouped['stock_manual_oem_clear'] += sum(
                bool(p.oem_provenance and not p.oem_number) for p in parts
            )
            linked = {r.part_id: r for r in entries if r.part_id is not None}
            grouped['stock_linked_to_dismantling_row'] += sum(p.id in linked for p in parts)
            grouped['stock_linked_valid_oem_ref_without_oem'] += sum(
                1 for p in parts
                if not p.oem_number and p.id in linked
                and auto_oem.transferable_reference(refs.get(linked[p.id].id))
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
            elif automatic:
                grouped['vehicles_with_source_identity'] += 1
                reasons['has_automatic_catalogue_identity'] += 1
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
            "coverage": {
                "plan_percent": _percent(grouped['valid_oem_refs'], grouped['included_rows']),
                "stock_percent": _percent(grouped['eligible_stock_with_oem'], grouped['eligible_stock_parts']),
            },
            "classification": "read_only_diagnostic_not_fitment",
        })
    return {"status": "reported", "read_only": True,
            "external_requests": 0, "provider_credits": 0,
            "vehicles": report}


def workspace_stock_audit(db, account_id, vehicle_id=None):
    """Group live warehouse cards within the requested user's active workspace."""
    from sqlalchemy import case, func
    from app.models import Category

    filters = [Part.account_id == account_id, Part.archived.is_(False),
               Part.quantity > 0, Part.availability != 'absent']
    if vehicle_id is not None:
        filters.append(Part.vehicle_id == vehicle_id)

    status = Part.oem_provenance['status'].as_string()
    source = Part.oem_provenance['source'].as_string()
    manual = (Part.oem_number != '') & (
        (source == 'manual') | (status == 'user_selected_cross_reference') | source.is_(None)
    )
    statement = (
        select(Part.vehicle_id, Vehicle.manufacturer, Category.name.label('category'),
               func.count().label('positions'),
               func.sum(case((Part.oem_number != '', 1), else_=0)).label('with_oem'),
               func.sum(case((manual, 1), else_=0)).label('manual_oem'))
        .select_from(Part)
        .outerjoin(Vehicle, (Vehicle.id == Part.vehicle_id) & (Vehicle.account_id == account_id))
        .outerjoin(Category, (Category.id == Part.category_id) & (Category.account_id == account_id))
        .where(*filters).group_by(Part.vehicle_id, Vehicle.manufacturer, Category.name)
    )
    total = Counter()
    manufacturers = {}
    categories = {}
    vehicles = {}
    for row in db.execute(statement):
        counts = {'positions':row.positions,'with_oem':row.with_oem,'manual_oem':row.manual_oem}
        total.update(counts)
        manufacturers.setdefault(row.manufacturer, Counter()).update(counts)
        categories.setdefault(row.category, Counter()).update(counts)
        vehicles.setdefault(row.vehicle_id, Counter()).update(counts)
    def summary(counts):
        return {**counts,'positions':counts['positions'],'with_oem':counts['with_oem'],
                'manual_oem':counts['manual_oem'],'coverage_percent':_percent(counts['with_oem'],counts['positions'])}
    return {'read_only':True,'stock':summary(total),
            'manufacturers':[{'manufacturer':key,**summary(counts)} for key,counts in manufacturers.items()],
            'categories':[{'category':key,**summary(counts)} for key,counts in categories.items()],
            'vehicles':[{'vehicle_id':key,**summary(counts)} for key,counts in vehicles.items()]}
