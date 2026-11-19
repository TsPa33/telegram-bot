"""Paid VIN command contract — no provider or wallet calls until an audited release.

This module intentionally has NO callable payment provider. Settlement must be
implemented in the central Billing service, not in Warehouse PostgreSQL.
"""
import re
from dataclasses import dataclass
from fastapi import HTTPException

PRICE_MINOR = 5000  # 50.00 UAH
CURRENCY = "UAH"
PRODUCT = "warehouse.vin.enrichment"
VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
REQUEST_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{16,80}$")
USEFUL_FIELDS = frozenset({
    "year", "body_class", "transmission", "engine", "engine_code",
    "engine_displacement_l", "engine_power_kw", "fuel_type", "vehicle_type",
})


def quote(vin: str):
    normalized = vin.strip().upper()
    if not VIN_PATTERN.fullmatch(normalized):
        raise HTTPException(422, "Некоректний VIN")
    return {
        "vin": normalized,
        "product": PRODUCT,
        "amount_minor": PRICE_MINOR,
        "currency": CURRENCY,
        "price_label": "50 грн",
        "checkout_available": False,
        "requires_confirmation": True,
        "settlement_policy": "Захоплення резерву тільки за нові корисні підтверджені поля; інакше резерв повертається.",
        "blocker": "Оплата вимкнена: не підключено перевірений контракт гаманця й VIN-провайдера.",
    }


def require_paid_vin_ready():
    # Fail closed regardless of any Warehouse environment variables. A later
    # reviewed change must implement an audited Billing and paid VIN transport.
    raise HTTPException(503, "Розширений VIN-пошук поки недоступний. 50 грн не списано.")


def validate_request_key(key):
    if not REQUEST_KEY_PATTERN.fullmatch(key or ""):
        raise HTTPException(422, "Некоректний ключ операції")


@dataclass(frozen=True)
class PaidVINOutcome:
    """Provider-independent release decision. No actual money movements here."""
    new_fields: tuple[str, ...]
    charge: bool


def settlement_decision(previous: dict, candidate: dict) -> PaidVINOutcome:
    """Conservatively charge only for missing, useful, explicitly provided data.

    Do not overwrite conflicts or treat a VIN provider success flag as value.
    Year must be model-year-like integer; remaining fields must be nonempty.
    """
    if not isinstance(previous, dict) or not isinstance(candidate, dict):
        raise ValueError("Expected normalized VIN field dictionaries")
    useful = []
    for key in sorted(USEFUL_FIELDS):
        old, new = previous.get(key), candidate.get(key)
        if old is not None and str(old).strip():
            continue
        if new is None or not str(new).strip() or str(new).strip().lower() in (
            "unknown", "n/a", "none", "null",
        ):
            continue
        if key == "year" and (
            isinstance(new, bool)
            or not str(new).isdigit()
            or not 1886 <= int(new) <= 2100
        ):
            continue
        useful.append(key)
    return PaidVINOutcome(tuple(useful), bool(useful))


def payment_keys(workspace: str, vin: str):
    """Deterministic wallet command keys, scoped by central billing account.

    The same VIN must not be charged twice. Actual Billing must enforce the
    unique (account, operation key) index and persist the receipt transactionally.
    """
    normalized = quote(vin)["vin"]
    import hashlib
    digest = hashlib.sha256((workspace + ":" + normalized + ":" + PRODUCT).encode()).hexdigest()
    return {stage: f"vin:{stage}:{digest[:40]}" for stage in ("reserve", "capture", "release")}


def next_state(current: str, event: str) -> str:
    """Idempotent operation state machine; never capture twice."""
    transitions = {
        ("quoted", "reserve_confirmed"): "reserved",
        ("reserved", "useful_result"): "captured",
        ("reserved", "no_useful_result"): "released",
        ("reserved", "provider_failure"): "released",
        ("quoted", "cancel"): "cancelled",
    }
    if (current, event) in transitions:
        return transitions[(current, event)]
    if (current, event) in {
        ("reserved", "reserve_confirmed"),
        ("captured", "useful_result"),
        ("released", "no_useful_result"),
        ("released", "provider_failure"),
        ("cancelled", "cancel"),
    }:
        return current
    raise ValueError(f"Forbidden VIN payment transition: {current} / {event}")


def reusable_receipt(receipt: dict | None, *, workspace: str, vin: str,
                     provider_version: str, now_epoch: int) -> bool:
    """Billing-verified receipt eligibility; never reuse data across tenants.

    Storage, expiry and license permission are owned by the future gateway.
    Passing an untrusted client-side receipt is forbidden by the API design.
    """
    if not isinstance(receipt, dict):
        return False
    return (
        receipt.get("workspace_id") == workspace
        and receipt.get("vin") == quote(vin)["vin"]
        and receipt.get("product") == PRODUCT
        and receipt.get("provider_version") == provider_version
        and receipt.get("financial_status") == "captured"
        and receipt.get("license_allows_reuse") is True
        and type(receipt.get("expires_at_epoch")) is int
        and receipt["expires_at_epoch"] > now_epoch
        and isinstance(receipt.get("confirmed_fields"), dict)
        and bool(set(receipt["confirmed_fields"]) & USEFUL_FIELDS)
    )
