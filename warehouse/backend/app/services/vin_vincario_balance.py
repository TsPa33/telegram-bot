"""Vincario 3.2 balance-only diagnostic.

No VIN decode, no wallet use, and no automatic requests. This is an explicit
platform-admin-only action. Credentials never appear in the response or logs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://api.vincario.com/3.2/"
BALANCE_KEYS = (
    "API Decode", "API Stolen Check", "API Vehicle Market Value",
    "API OEM VIN Lookup", "API OEM Service History",
)
MAX_RESPONSE_BYTES = 8192


def configured() -> bool:
    return bool(
        os.getenv("WAREHOUSE_VINCARIO_API_KEY", "").strip()
        and os.getenv("WAREHOUSE_VINCARIO_SECRET_KEY", "").strip()
    )


def _endpoint(api_key: str, secret_key: str) -> str:
    # Official API v3.2: for a request without VIN:
    # sha1("balance|API_KEY|SECRET_KEY").hexdigest()[:10]
    checksum = hashlib.sha1(
        f"balance|{api_key}|{secret_key}".encode("utf-8")
    ).hexdigest()[:10]
    return f"{BASE_URL}{api_key}/{checksum}/balance.json"


def fetch_balance() -> dict:
    """Perform exactly one read-only balance request on explicit invocation."""
    key = os.getenv("WAREHOUSE_VINCARIO_API_KEY", "").strip()
    secret = os.getenv("WAREHOUSE_VINCARIO_SECRET_KEY", "").strip()
    if not key or not secret:
        return {"status": "not_configured", "balances": {}}
    if os.getenv("WAREHOUSE_ENV", "").strip() != "staging":
        return {"status": "staging_only", "balances": {}}
    request = Request(
        _endpoint(key, secret),
        headers={"Accept": "application/json", "User-Agent": "CarPotWarehouse/1.0"},
    )
    try:
        with urlopen(request, timeout=12) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # Do NOT stringify exception: HTTPError includes credential-bearing URL.
        return {"status": {
            400: "bad_request", 401: "unauthorized", 402: "quota_unavailable",
            403: "forbidden", 404: "not_found", 429: "rate_limited",
        }.get(exc.code, "provider_http_error"), "balances": {}}
    except (OSError, TimeoutError, URLError):
        return {"status": "provider_unavailable", "balances": {}}
    if len(body) > MAX_RESPONSE_BYTES:
        return {"status": "invalid_response", "balances": {}}
    try:
        data = json.loads(body)
    except (UnicodeError, ValueError, TypeError):
        return {"status": "invalid_response", "balances": {}}
    return parse_balance(data)


# Certain Vincario account types use different naming for decoder credits.
# Do not extrapolate an account's free trial from unrelated API balances.
DECODER_BALANCE_ALIASES = (
    "API Decode",
    "API VIN Decode",
    "VIN Decode",
    "VIN Decoder",
    "API VIN Decoder",
)
_SAFE_LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,55}$")
_SECRET_LABEL = re.compile(r"key|token|secret|auth|password|session|email|phone|vin_number", re.I)


def _known_balance_keys(payload: dict) -> list[str]:
    """Return only safe API-category NAMES, never raw values or identifiers."""
    out = []
    for name in payload:
        if not isinstance(name, str) or not _SAFE_LABEL.fullmatch(name):
            continue
        if _SECRET_LABEL.search(name):
            continue
        if name in BALANCE_KEYS or "decode" in name.lower() or (
            name.startswith("API ") and any(word in name.lower() for word in ("balance", "credit", "lookup"))
        ):
            out.append(name)
        if len(out) >= 12:
            break
    return out


def parse_balance(payload) -> dict:
    """Report VIN Decode separately, preserving 'missing' vs actual zero.

    The diagnostic reveals only selected field names and coarse types, never
    credential-bearing values or the unrestricted provider response.
    """
    if not isinstance(payload, dict):
        return {"status": "invalid_response", "balances": {},
                "decode_balance_status": "unknown", "decode_balance": None,
                "provider_balance_fields": []}
    balances = {}
    for name in BALANCE_KEYS:
        value = payload.get(name)
        if type(value) is int and 0 <= value <= 10_000_000:
            balances[name] = value

    alias = next((name for name in DECODER_BALANCE_ALIASES
                  if name in payload), None)
    raw_decoder = payload.get(alias) if alias is not None else None
    decode_balance = (raw_decoder if type(raw_decoder) is int
                      and 0 <= raw_decoder <= 10_000_000 else None)
    decode_balance_status = (
        "not_returned" if alias is None
        else "available" if decode_balance is not None
        else "unexpected_value_type"
    )
    if alias and decode_balance is not None:
        balances.setdefault("API Decode", decode_balance)

    diagnostic = []
    for name in _known_balance_keys(payload):
        value = payload[name]
        kind = ("integer" if type(value) is int
                else "text" if isinstance(value, str)
                else "object" if isinstance(value, dict)
                else "array" if isinstance(value, list)
                else "other")
        diagnostic.append({"name": name, "type": kind})
    return {
        "status": "reported" if balances else "unexpected_schema",
        "balances": balances,
        "decode_balance": decode_balance,
        "decode_balance_status": decode_balance_status,
        "decode_balance_field": alias,
        "provider_balance_fields": diagnostic,
        "paid_requests_enabled": False,
        "free_trial_verified": False,
        "note": "Баланс не підтверджує безкоштовну квоту. VIN Decode залишається вимкненим.",
    }
