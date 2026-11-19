"""Manual Vincario Free Demo validation on exactly three approved control VINs.

No automatic integration with /vehicles/vin/decode or CarPot Billing.
A successful call consumes the provider's *free* quota, confirmed by the
customer's Vincario Free Demo activation email (20 VIN Decode credits).
The balance-before gate prevents the demo from being exhausted by this feature.
"""
from __future__ import annotations

from hashlib import sha1
from json import loads
from os import getenv
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.vin_vincario_balance import fetch_balance

CONTROL_VINS = frozenset({
    "XLRTE47MS0E774889",  # DAF XF 2007
    "YV4A22PK2G1092943",  # Volvo XC90 2016
    "YV4L12RK6N1970668",  # Volvo XC60 2022
})
INITIAL_FREE_CREDITS = 20
RESERVE_AT_LEAST = 17
LABELS = {
    "Make": "manufacturer", "Model": "model", "Model Year": "year",
    "Product Type": "vehicle_type", "Body": "body_class", "Drive": "drive_type",
    "Engine Displacement (ccm)": "engine_displacement_cc",
    "Engine Code": "engine_code", "Engine Model": "engine",
    "Engine Power (kW)": "engine_power_kw",
    "Fuel Type - Primary": "fuel_type",
    "Fuel Type - Secondary": "fuel_secondary",
    "Transmission": "transmission", "Transmission (full)": "transmission_code",
    "Trim": "trim", "Variant": "variant", "Series": "series",
    "Number of Doors": "doors", "Number of Seats": "seats",
    "Plant Country": "plant_country", "Make Logo": "make_logo",
}
_lock = Lock()
# In-process duplicate protection, not durable accounting. Balance floor is
# the actual credit safety net. A full product integration needs a DB ledger.
_results = {}


def _safe_text(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    value = str(value).strip()
    return value if value and value.lower() not in ("unknown", "null", "none", "n/a") and len(value) <= 200 else None


def parse_decode(document, vin):
    if not isinstance(document, dict) or not isinstance(document.get("decode"), list):
        return {"status": "unexpected_schema", "vehicle": {}, "fields": [], "missing": []}
    raw = {}
    for row in document["decode"][:200]:
        if not isinstance(row, dict):
            continue
        label = row.get("label")
        if isinstance(label, str) and label in LABELS:
            value = _safe_text(row.get("value"))
            if value is not None:
                raw[LABELS[label]] = value
    if "year" in raw:
        if not raw["year"].isdigit() or not 1886 <= int(raw["year"]) <= 2100:
            del raw["year"]
        else:
            raw["year"] = int(raw["year"])
    # The website's comparison prices are NOT the exact VIN's trim or power.
    if "engine_displacement_cc" in raw:
        raw["engine_displacement_cc"] = raw["engine_displacement_cc"].replace(",", "")
    # A remote Make Logo URL is informative, but no right to copy/cache it is
    # implied. Do not return URL to UI to encourage unauthorized image reuse.
    logo_available = "make_logo" in raw
    raw.pop("make_logo", None)
    essentials = ("manufacturer","model","year","body_class",
                  "engine_displacement_cc","fuel_type","transmission","drive_type",
                  "engine_code","transmission_code")
    return {
        "status": "reported" if raw else "no_useful_fields",
        "vehicle": raw,
        "fields": sorted(raw),
        "missing": [field for field in essentials if field not in raw],
        "logo_field_available": logo_available,
        "vehicle_count": len(document["decode"]),
    }


def _endpoint(vin, key, secret):
    control = sha1(f"{vin}|decode|{key}|{secret}".encode("utf-8")).hexdigest()[:10]
    return f"https://api.vincario.com/3.2/{key}/{control}/decode/{vin}.json"


def readiness():
    return {
        "staging": getenv("WAREHOUSE_ENV") == "staging",
        "credentials_present": bool(getenv("WAREHOUSE_VINCARIO_API_KEY", "").strip()
                                    and getenv("WAREHOUSE_VINCARIO_SECRET_KEY", "").strip()),
        "supported_vins": sorted(CONTROL_VINS),
        "locally_cached_vins": sorted(_results),
        "free_demo_initial_credits": INITIAL_FREE_CREDITS,
        "minimum_balance_before_call": RESERVE_AT_LEAST + 1,
        "automatic_enabled": False,
        "carpot_billing_enabled": False,
    }


def preview(vin: str, *, acknowledged: bool):
    vin = vin.strip().upper()
    if vin not in CONTROL_VINS:
        return {"status": "vin_not_allowlisted"}
    if not acknowledged:
        return {"status": "confirmation_required"}
    if getenv("WAREHOUSE_ENV") != "staging":
        return {"status": "staging_only"}
    key = getenv("WAREHOUSE_VINCARIO_API_KEY", "").strip()
    secret = getenv("WAREHOUSE_VINCARIO_SECRET_KEY", "").strip()
    if not key or not secret:
        return {"status": "not_configured"}
    with _lock:
        if vin in _results:
            return dict(_results[vin], from_cache=True)
        before = fetch_balance()
        remaining = before.get("decode_balance")
        if type(remaining) is not int or not (RESERVE_AT_LEAST < remaining <= INITIAL_FREE_CREDITS):
            return {"status": "insufficient_verified_demo_balance",
                    "balance_before": remaining if type(remaining) is int else None}
        request = Request(_endpoint(vin, key, secret),
            headers={"Accept": "application/json", "User-Agent": "CarPotWarehouse/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read(160001)
        except HTTPError as exc:
            # Never return URLs containing key/checksum.
            return {"status": {401: "unauthorized", 402: "credits_unavailable",
                               403: "forbidden", 404: "not_found",
                               429: "rate_limited"}.get(exc.code, "provider_http_error"),
                    "balance_before": remaining}
        except (OSError, TimeoutError, URLError):
            return {"status": "network_unavailable", "balance_before": remaining}
        if len(body) > 160000:
            return {"status": "response_too_large", "balance_before": remaining}
        try:
            result = parse_decode(loads(body), vin)
        except (ValueError, TypeError, UnicodeError):
            return {"status": "invalid_json", "balance_before": remaining}
        result.update(vin=vin, balance_before=remaining)
        # If provider returns a usable result, cache it; a later call may
        # recheck balance but must not trigger another paid decode in-process.
        # Persisting across deployments requires the later DB-backed ledger.
        _results[vin] = dict(result)
        result["from_cache"] = False
        after = fetch_balance()
        result["balance_after"] = after.get("decode_balance")
        return result
