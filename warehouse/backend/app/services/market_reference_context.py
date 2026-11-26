from app.models import Vehicle
from app.services.price_guidance import parts_for


def lookup_context(db, account, part_id):
    part = parts_for(db, account, [part_id])[0]
    vehicle = db.get(Vehicle, part.vehicle_id) if part.vehicle_id else None
    if vehicle and vehicle.account_id != account:
        vehicle = None
    return dict(oem=part.oem_number, name=part.name, condition=part.condition,
                manufacturer=vehicle.manufacturer if vehicle else "",
                model=vehicle.model if vehicle else "",
                year=vehicle.year if vehicle else None,
                vehicle_id=part.vehicle_id)
