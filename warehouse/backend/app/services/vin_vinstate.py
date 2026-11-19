"""VINState diagnostic adapter. NOT part of automatic or paid VIN flows.

API responses may consume VINState credits after included quota is exhausted.
Never call decode unless the independent staging diagnostic gate is enabled.
The API key is never returned, stored in VIN details, or written to logs.
"""
from __future__ import annotations

import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
MAX_BYTES = 128_000
API_ORIGIN = "https://vinstate.com/api/v1/vin/"
FIELD_PATHS = {
    "manufacturer": (("vehicle", "make"), ("wmi", "make"), ("wmi", "manufacturer")),
    "model": (("vehicle", "model"),),
    "year": (("vehicle", "model_year"), ("vehicle", "year")),
    "body_class": (("vehicle", "body_type"), ("vehicle", "body_style")),
    "transmission": (("vehicle", "transmission"),),
    "engine": (("vehicle", "engine"), ("vehicle", "engine_model")),
    "engine_displacement_l": (("vehicle", "engine_displacement_l"),),
    "fuel_type": (("vehicle", "fuel_type"),),
    "drive_type": (("vehicle", "drive_type"),),
    "vehicle_type": (("vehicle", "vehicle_type"),),
}


def test_gate_enabled() -> bool:
    """A token alone must never enable billable requests."""
    return (
        os.getenv("WAREHOUSE_ENV") == "staging"
        and os.getenv("WAREHOUSE_VINSTATE_TEST_ENABLED", "false").lower() == "true"
        and bool(os.getenv("WAREHOUSE_VINSTATE_API_KEY", "").strip())
    )


def _pick(decoded: dict, options: tuple[tuple[str, str], ...]):
    for section, key in options:
        group = decoded.get(section)
        if isinstance(group, dict):
            value = group.get(key)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                value = str(value).strip()
                if value and value.casefold() not in {"unknown", "none", "null", "n/a", "-"} and len(value) <= 160:
                    return value
    return None



# Bounded diagnostic includes only schema paths and coarse types, NEVER values.
# Avoid recording secrets, VINs, email addresses or uncontrolled dynamic keys.
SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,47}$")
SENSITIVE = re.compile(r"vin|token|secret|key|auth|email|phone|name|address|password", re.I)


def response_shape(payload: dict) -> dict:
    """Structure-only inventory of known provider sections, no source values."""
    if not isinstance(payload, dict):
        return {"sections": [], "fields": [], "billing_meta_present": False}
    rows = payload.get("data")
    row = rows[0] if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else {}
    decoded = row.get("decoded")
    decoded = decoded if isinstance(decoded, dict) else {}
    sections, fields = [], []
    for name, group in sorted(decoded.items()):
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or SENSITIVE.search(name):
            continue
        if not isinstance(group, dict):
            continue
        sections.append(name)
        for key, value in sorted(group.items()):
            if len(fields) >= 60:
                break
            if not isinstance(key, str) or not SAFE_NAME.fullmatch(key) or SENSITIVE.search(key):
                continue
            kind = "object" if isinstance(value, dict) else "array" if isinstance(value, list) else "number" if type(value) in (int, float) else "text" if isinstance(value, str) else "boolean" if isinstance(value, bool) else "null"
            fields.append({"path": name + "." + key, "type": kind, "populated": value is not None and value != ""})
    meta = payload.get("meta")
    return {"sections": sections[:20], "fields": fields,
            "billing_meta_present": isinstance(meta, dict),
            "data_rows": len(rows) if isinstance(rows, list) else 0}

def parse(payload: dict, vin: str) -> dict:
    """Only named, explicit attributes are accepted; no inference from car label."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return {"vehicle": {}, "status": "invalid_or_empty", "billing": {}}
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return {"vehicle": {}, "status": "invalid_or_empty", "billing": {}}
    row = rows[0]
    if str(row.get("vin", "")).strip().upper() != vin:
        return {"vehicle": {}, "status": "vin_mismatch", "billing": {}}
    decoded = row.get("decoded")
    if not isinstance(decoded, dict):
        return {"vehicle": {}, "status": "invalid_or_empty", "billing": {}}
    values = {}
    for name, paths in FIELD_PATHS.items():
        val = _pick(decoded, paths)
        if val is not None:
            if name == "year":
                if not val.isdigit() or not 1886 <= int(val) <= 2100:
                    continue
                values[name] = int(val)
            else:
                values[name] = val
    meta = payload.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    # Record billing metadata only. It is NOT evidence that we charged the user.
    billing = {
        "billed_by_vinstate": meta.get("billed") is True,
        "funding_source": meta.get("funding_source") if meta.get("funding_source") in ("included", "credits") else "unknown",
        "included_requests_charged": meta.get("included_requests_charged") if type(meta.get("included_requests_charged")) is int else None,
        "charged_credits": meta.get("charged_credits") if type(meta.get("charged_credits")) is int else None,
    }
    label = _pick(decoded, (("vehicle", "car"),))
    # year.year_code is a VIN model-year *code*, not a year. Do not infer a
    # calendar year: it is cyclic and needs manufacturer/model context.
    # WMI alone is an identifier, not an enhanced vehicle specification.
    identifier_only = set(values) <= {"manufacturer"}
    status = ("identifier_only" if values and identifier_only
              else "reported" if values else "label_only_or_empty")
    return {
        "vehicle": values,
        "status": status,
        "vehicle_label": label,
        "billing": billing,
        "response_shape": response_shape(payload),
    }


def decode(vin: str) -> dict:
    vin = vin.strip().upper()
    if not VIN_PATTERN.fullmatch(vin):
        raise ValueError("Invalid VIN")
    if not test_gate_enabled():
        raise RuntimeError("VINState diagnostic is disabled")
    token = os.environ["WAREHOUSE_VINSTATE_API_KEY"].strip()
    request = Request(API_ORIGIN + vin, headers={
        "Accept": "application/json",
        "Authorization": "Bearer " + token,
        "User-Agent": "CarPotWarehouse/1.0",
    })
    try:
        with urlopen(request, timeout=18) as response:
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        statuses = {401: "unauthorized", 402: "no_included_quota_or_credits", 403: "forbidden",
                    404: "not_found", 422: "invalid_vin", 429: "rate_limited", 503: "unavailable"}
        return {"vehicle": {}, "status": statuses.get(exc.code, "http_error"), "billing": {}}
    except (TimeoutError, OSError, URLError):
        return {"vehicle": {}, "status": "network_unavailable", "billing": {}}
    if len(raw) > MAX_BYTES:
        return {"vehicle": {}, "status": "oversized_response", "billing": {}}
    try:
        return parse(json.loads(raw), vin)
    except (ValueError, UnicodeError, TypeError):
        return {"vehicle": {}, "status": "invalid_json", "billing": {}}
