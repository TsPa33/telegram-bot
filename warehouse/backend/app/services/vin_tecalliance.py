"""TecAlliance VIN v1 offline normalization and preflight. No paid transport.

Contract references:
https://vehicle-identification.tecalliance.services/documentation/news
https://vehicle-identification.tecalliance.services/documentation/vin/v1/attributes

VIN may yield MULTIPLE KTypes/NTypes. Never silently select a candidate.
No request is allowed until vendor-specific auth, billing, territory and license
terms have been verified and separately implemented.
"""
from __future__ import annotations

import os
import re

VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
COUNTRY = re.compile(r"^[A-Z]{2}$")
MAX_CANDIDATES = 40


def normalize_vin(vin: str) -> str:
    value = vin.strip().upper()
    if not VIN.fullmatch(value):
        raise ValueError("VIN must have exactly 17 valid characters")
    return value


def _object(value):
    return value if isinstance(value, dict) else {}


def _text(value):
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    value = str(value).strip()
    return value if value and value.lower() not in {"unknown", "null", "none", "n/a"} and len(value) <= 160 else None


def _integer(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return int(text) if text.isdigit() and len(text) <= 12 else None


def _year_from_period(value):
    """A salesStartDate is a range boundary, not an individual production year."""
    text = _text(value)
    return text if text and re.fullmatch(r"\d{6}", text) else None


def _list_of_objects(value):
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)][:MAX_CANDIDATES]
    return []


def _candidate(item):
    info = _object(item.get("vehicleInformation"))
    if not info:
        info = item
    engine_rows = _list_of_objects(item.get("engine") or item.get("engines"))
    gearbox_rows = _list_of_objects(item.get("gearbox") or item.get("gearboxes"))
    # Vendor calls 'gearbox.type' transmission style in the published v1 schema.
    engine = engine_rows[0] if len(engine_rows) == 1 else {}
    gearbox = gearbox_rows[0] if len(gearbox_rows) == 1 else {}
    ktype = _integer(info.get("ktype"))
    ntype = _integer(info.get("ntype"))
    make = _text(info.get("make"))
    model = _text(info.get("model"))
    vehicle = {}
    pairs = {
        "manufacturer": make,
        "model": model,
        "body_class": _text(info.get("bodyName")),
        "engine_code": _text(engine.get("code")),
        "engine_displacement_l": _text(engine.get("capacityLiters") or info.get("capacityLiters")),
        "fuel_type": _text(engine.get("fuel") or info.get("energy")),
        "engine_power_kw": _text(info.get("powerKW")),
        "transmission": _text(gearbox.get("type")),
        "doors": _text(info.get("numberOfDoors")),
        "drive_type": _text(info.get("driveType")),
        "vehicle_type": "Вантажний автомобіль" if ntype and not ktype else "Легковий автомобіль" if ktype and not ntype else None,
    }
    for key, value in pairs.items():
        if value is not None:
            vehicle[key] = value
    return {
        "ktype": ktype,
        "ntype": ntype,
        "linkage_type": _text(info.get("linkageTargetType")),
        "vehicle": vehicle,
        "sales_period": {
            "start": _year_from_period(info.get("salesStartDate")),
            "end": _year_from_period(info.get("salesEndDate")),
        },
        "engine_options": len(engine_rows),
        "gearbox_options": len(gearbox_rows),
        "requires_selection": len(engine_rows) > 1 or len(gearbox_rows) > 1,
    }


def normalize_response(payload: dict) -> dict:
    """Works only with explicitly documented VRM/VIN-style vehicles envelope.

    No guessing year from sales dates, no factory-fitment claim, no paid calls.
    """
    if not isinstance(payload, dict):
        raise ValueError("Invalid response envelope")
    container = _object(payload.get("data"))
    vehicles = payload.get("vehicles", container.get("vehicles"))
    if not isinstance(vehicles, list):
        raise ValueError("TecAlliance 'vehicles' array missing")
    if len(vehicles) > MAX_CANDIDATES:
        raise ValueError("Candidate list too large for safe preview")
    result = [_candidate(row) for row in vehicles if isinstance(row, dict)]
    # Candidate without KType/NType is NOT a verified TecDoc match.
    result = [r for r in result if r["ktype"] is not None or r["ntype"] is not None]
    return {
        "status": "no_match" if not result else "multiple_candidates" if len(result) > 1 else "single_candidate",
        "candidates": result,
        "candidate_count": len(result),
        "requires_user_selection": len(result) > 1 or bool(result and result[0]["requires_selection"]),
        "factory_configuration_verified": False,
    }


def readiness() -> dict:
    # Code-only phase. A key alone MUST NOT enable calls.
    country = os.getenv("WAREHOUSE_TECALLIANCE_COUNTRY", "").strip().upper()
    return {
        "provider": "TecAlliance Vehicle Identification VIN v1",
        "credentials_configured": bool(os.getenv("WAREHOUSE_TECALLIANCE_API_KEY", "").strip()),
        "country_valid": bool(COUNTRY.fullmatch(country)),
        "country": country if COUNTRY.fullmatch(country) else None,
        "transport_enabled": False,
        "billing_enabled": False,
        "live_calls_permitted": False,
        "reason": "Потрібні офіційні credentials, підтверджений auth-контракт, країна, тариф та ліцензія.",
    }
