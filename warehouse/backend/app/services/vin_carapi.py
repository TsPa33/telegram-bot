"""Optional CarAPI.dev VIN fallback (free-tier token only; never auto-enrolled).

Official contract: https://docs.carapi.dev/endpoints/vin-decode
Keep derived response in ephemeral VIN cache only; the provider limits retention.
"""
import json
import os
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

MAX_BYTES = 120_000


def is_enabled():
    return (os.getenv("WAREHOUSE_CARAPI_ENABLED", "false").strip().lower() == "true"
            and bool(os.getenv("WAREHOUSE_CARAPI_TOKEN", "").strip()))


def _valid(value):
    return value is not None and isinstance(value, (int, float, str)) and str(value).strip() not in ("", "null", "N/A", "None")


def _year(value):
    if not _valid(value) or not str(value).isdigit():
        return None
    year = int(value)
    return year if 1886 <= year <= 2100 else None


def decode(vin):
    """Fetch once, bounded. None means no usable verified vehicle data."""
    if not is_enabled():
        return None
    token = os.environ["WAREHOUSE_CARAPI_TOKEN"].strip()
    url = ("https://api.carapi.dev/v1/vin-decode/" + vin
           + "?token=" + quote(token, safe=""))
    request = Request(url, headers={"Accept": "application/json",
                                    "User-Agent": "CarPotWarehouse/1.0"})
    try:
        with urlopen(request, timeout=6) as response:
            body = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        if exc.code in (400, 403, 404, 429):
            return None
        raise
    if len(body) > MAX_BYTES:
        raise ValueError("VIN provider response exceeds maximum size")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Invalid VIN response")
    if payload.get("success") is False or payload.get("error"):
        return None

    # The provider documents both specifications and success/data payload shapes.
    if isinstance(payload.get("specifications"), dict):
        spec = payload["specifications"]
        mapping = {
            "manufacturer": spec.get("make"),
            "model": spec.get("model"),
            "fuel_type": spec.get("fuel"),
            "transmission": spec.get("transmission"),
            "body_class": spec.get("bodyStyle"),
            "drive_type": spec.get("drivetrain"),
        }
        # The provider explicitly declares these body styles as vehicle categories.\n        vehicle_type = {"TRUCK": "Вантажний автомобіль", "BUS": "Автобус",\n                        "MOTORCYCLE": "Мотоцикл"}.get(str(spec.get("bodyStyle", "")).upper())\n        if vehicle_type:\n            mapping["vehicle_type"] = vehicle_type\n        if str(spec.get("enginePowerUnit", "")).casefold() == "kw":
            mapping["engine_power_kw"] = spec.get("enginePower")
        # registrationDate is not the manufacture/model year; do not infer year.
    elif isinstance(payload.get("data"), dict):
        spec = payload["data"]
        mapping = {
            "manufacturer": spec.get("make"),
            "model": spec.get("model"),
            "year": _year(spec.get("year")),
            "fuel_type": spec.get("fuel_type"),
            "transmission": spec.get("transmission"),
            "body_class": spec.get("body_type"),
            "drive_type": spec.get("drive_type"),
            "engine": spec.get("engine"),
        }
    else:
        return None
    # Never retain plate, VIN, feature payloads or the provider raw response.
    mapped = {k: str(v).strip() if k != "year" else v for k, v in mapping.items()
              if _valid(v) and len(str(v)) <= 200}
    # A make without model cannot support assignment of any model-specific specs.
    if not (mapped.get("manufacturer") and mapped.get("model")):
        return None
    return mapped
