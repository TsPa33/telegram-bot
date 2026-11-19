"""Vincario 3.2 balance-only diagnostic.

No VIN decode, no wallet use, and no automatic requests. This is an explicit
platform-admin-only action. Credentials never appear in the response or logs.
"""
from __future__ import annotations

import hashlib
import json
import os
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


def parse_balance(payload) -> dict:
    """Strict allowlist of vendor balance categories; never return raw JSON."""
    if not isinstance(payload, dict):
        return {"status": "invalid_response", "balances": {}}
    # 3.2 Swagger describes a flat object of product name -> available balance.
    # Some accounts may return nested balance; this is intentionally NOT guessed.
    balances = {}
    for name in BALANCE_KEYS:
        value = payload.get(name)
        if type(value) is int and 0 <= value <= 10_000_000:
            balances[name] = value
    if not balances:
        return {"status": "unexpected_schema", "balances": {}}
    return {
        "status": "reported",
        "balances": balances,
        "paid_requests_enabled": False,
        "note": (
            "Це залишок API, а не підтвердження безкоштовного статусу. "
            "Платне VIN-декодування CarPot вимкнене."
        ),
    }
