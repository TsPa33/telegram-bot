"""Durable, auditable VIN evidence. No provider calls, no billing.

User-provided report reconstructions are marked distinctly from actual API JSON.
Do not silently treat this evidence as verified OEM or factory fitment.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.vin_evidence import VinEvidenceSnapshot

VERSION="vincario-3.2"
PROVIDER="vincario"
ESSENTIALS=("manufacturer","model","year","body_class","engine_displacement_cc",
            "fuel_type","transmission","drive_type","engine_code","transmission_code")

# Reconstructed exactly from the user's own successful Free Demo UI snapshots;
# these are not stored copies of original provider API JSON. All fields are
# informational; no engine/gearbox codes or compatibility are inferred.
CONTROL_REPORTS={
    "XLRTE47MS0E774889":{
        "manufacturer":"DAF","model":"XF","year":2007,
        "vehicle_type":"Truck","body_class":"Tractor",
        "drive_type":"Rear-wheel drive","engine_displacement_cc":"12902",
        "fuel_type":"Diesel","plant_country":"Netherlands","doors":"2","seats":"2"},
    "YV4A22PK2G1092943":{
        "manufacturer":"Volvo","model":"XC90","year":2016,
        "vehicle_type":"Car","body_class":"Sport Utility Vehicle (SUV)/Multi Purpose Vehicle (MPV)",
        "drive_type":"4x4 - Four-wheel drive","engine_displacement_cc":"1969",
        "fuel_type":"Gasoline","transmission":"Automatic",
        "plant_country":"Sweden","doors":"4","seats":"7"},
    "YV4L12RK6N1970668":{
        "manufacturer":"Volvo","model":"XC60","year":2022,
        "vehicle_type":"Car","body_class":"Sport Utility Vehicle (SUV)/Multi Purpose Vehicle (MPV)",
        "drive_type":"All wheel drive","engine_displacement_cc":"2000",
        "fuel_type":"Gasoline","fuel_secondary":"Electric",
        "plant_country":"Sweden"},
}


def get(db, vin):
    return db.scalar(select(VinEvidenceSnapshot).where(
        VinEvidenceSnapshot.provider==PROVIDER,
        VinEvidenceSnapshot.vin==vin.strip().upper(),
        VinEvidenceSnapshot.contract_version==VERSION))


def view(record):
    return {
        "status": record.status,
        "vin": record.vin,
        "vehicle": record.vehicle,
        "missing": record.missing,
        "from_durable_cache": True,
        "source": record.source,
        "observed_at": record.observed_at.isoformat(),
        "logo_field_available": record.logo_field_available,
        "balance_before": record.balance_before,
        "balance_after": record.balance_after,
        "provider": record.provider,
    }


def save(db, vin, result, source="vincario_api_trial"):
    vin=vin.strip().upper()
    if vin not in CONTROL_REPORTS:
        raise ValueError("Trial evidence may be saved only for approved VINs")
    old=get(db,vin)
    if old:
        return view(old)
    row=VinEvidenceSnapshot(
        provider=PROVIDER,vin=vin,contract_version=VERSION,
        source=source,status=result.get("status","reported"),
        vehicle=result["vehicle"],
        missing=result.get("missing",[]),
        logo_field_available=bool(result.get("logo_field_available",False)),
        balance_before=result.get("balance_before"),
        balance_after=result.get("balance_after"),
    )
    db.add(row)
    db.commit()
    return view(row)


def restore_control_reports(db):
    """One-time, explicit admin action; no network and no credit deduction.

    Do not replace existing provider-sourced evidence.
    """
    existing, created = [], []
    for vin, vehicle in CONTROL_REPORTS.items():
        if get(db,vin):
            existing.append(vin)
            continue
        result={"status":"reported","vehicle":dict(vehicle),
                "missing":[k for k in ESSENTIALS if k not in vehicle],
                "logo_field_available":True}
        save(db,vin,result,source="user_supplied_api_result_screenshot")
        created.append(vin)
    return {"created":created,"already_saved":existing,
            "provider_requests":0,"credits_spent":0,
            "evidence_note":"Відновлено з наданих скриншотів тесту, не з оригінального JSON."}
