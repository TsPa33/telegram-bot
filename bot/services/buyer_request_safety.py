import hashlib
import re
from dataclasses import asdict, dataclass


@dataclass(slots=True)
class BuyerRequestSafetyResult:
    fingerprint: str
    normalized_phone: str | None
    duplicate_window_seconds: int
    rate_limit_bucket: str
    suspicious: bool
    suspicious_reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_phone_for_safety(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    if len(digits) == 10 and digits.startswith("0"):
        return f"380{digits}"
    if len(digits) == 12 and digits.startswith("380"):
        return digits
    if 9 <= len(digits) <= 15:
        return digits
    return None


def build_request_fingerprint(
    *,
    phone: str | None,
    city: str | None,
    request_type: str | None,
    category: str | None,
    description: str | None,
    vin: str | None,
) -> str:
    normalized_description = re.sub(r"\s+", " ", (description or "").strip().lower())[:160]
    payload = "|".join(
        [
            normalize_phone_for_safety(phone) or "",
            (city or "").strip().lower(),
            (request_type or "").strip().lower(),
            (category or "").strip().lower(),
            (vin or "").strip().upper(),
            normalized_description,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def inspect_buyer_request_safety(
    *,
    phone: str | None,
    city: str | None,
    request_type: str | None,
    category: str | None,
    description: str | None,
    vin: str | None,
) -> BuyerRequestSafetyResult:
    normalized_phone = normalize_phone_for_safety(phone)
    reasons: list[str] = []
    normalized_description = (description or "").strip().lower()

    if not normalized_phone:
        reasons.append("invalid_phone")
    if len(normalized_description) < 12:
        reasons.append("short_description")
    if normalized_description.count("http://") + normalized_description.count("https://") > 1:
        reasons.append("multiple_links")
    if len(set(normalized_description.split())) <= 2 and len(normalized_description) > 30:
        reasons.append("repetitive_text")

    bucket_source = normalized_phone or (city or "unknown").strip().lower() or "unknown"

    return BuyerRequestSafetyResult(
        fingerprint=build_request_fingerprint(
            phone=phone,
            city=city,
            request_type=request_type,
            category=category,
            description=description,
            vin=vin,
        ),
        normalized_phone=normalized_phone,
        duplicate_window_seconds=900,
        rate_limit_bucket=f"buyer_request:{bucket_source}",
        suspicious=bool(reasons),
        suspicious_reasons=reasons,
    )
