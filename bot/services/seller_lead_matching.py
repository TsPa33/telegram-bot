from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(slots=True)
class SellerLeadMatchContext:
    seller_id: int
    seller_city: str | None
    specialization_tags: list[str]
    verified: bool
    premium_ready: bool


@dataclass(slots=True)
class SellerLeadScore:
    score: int
    city_match: bool
    specialization_match: bool
    request_type_match: bool
    premium_priority: bool
    routing_tier: str

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _contains_any(value: str | None, tags: Iterable[str]) -> bool:
    normalized = _norm(value)
    if not normalized:
        return False
    return any(_norm(tag) and _norm(tag) in normalized for tag in tags)


def score_seller_lead(
    *,
    seller_city: str | None,
    specialization_tags: Iterable[str],
    request_city: str | None,
    category: str | None,
    request_type: str | None,
    brand: str | None,
    model: str | None,
    urgency: str | None,
    verified: bool = False,
    premium_ready: bool = False,
) -> SellerLeadScore:
    tags = [tag for tag in specialization_tags if tag]
    city_match = bool(_norm(seller_city) and _norm(seller_city) == _norm(request_city))
    specialization_match = any(
        _contains_any(candidate, tags)
        for candidate in (category, brand, model)
    )
    request_type_match = _contains_any(request_type, tags)

    score = 0
    if city_match:
        score += 40
    if specialization_match:
        score += 30
    if request_type_match:
        score += 15
    if urgency == "today":
        score += 10
    if verified:
        score += 5
    if premium_ready:
        score += 5

    if premium_ready and score >= 55:
        routing_tier = "premium_ready"
    elif score >= 45:
        routing_tier = "strong_match"
    elif score >= 20:
        routing_tier = "broad_match"
    else:
        routing_tier = "fallback"

    return SellerLeadScore(
        score=score,
        city_match=city_match,
        specialization_match=specialization_match,
        request_type_match=request_type_match,
        premium_priority=premium_ready,
        routing_tier=routing_tier,
    )
