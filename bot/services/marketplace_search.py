"""Priority marketplace search for CarPot buyer AI search.

This service keeps the AI interpreter narrow: interpreted buyer intent is treated as
input signals, while CarPot owns all database search, prioritisation, routing and
UX explanations. The priority flow is intentionally dismantler-aware: missing exact
part inventory should lead to donor vehicles and seller specialization, not a dead
"nothing found" answer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from bot.database.repositories.marketplace_repo import (
    search_donor_vehicle_matches,
    search_exact_part_matches,
    search_seller_specialization_matches,
)

RESULT_EXACT_PART = "exact_part_match"
RESULT_DONOR_VEHICLE = "donor_vehicle_match"
RESULT_SELLER_SPECIALIZATION = "seller_specialization_match"
RESULT_REQUEST_FALLBACK = "marketplace_request_fallback"

STRONG_EXACT_THRESHOLD = 3
STRONG_DONOR_THRESHOLD = 3
STRONG_SPECIALIZATION_THRESHOLD = 2


@dataclass(slots=True)
class MarketplaceSearchDecision:
    """A transparent decision emitted by the marketplace engine."""

    step: int
    result_type: str
    title: str
    explanation: str
    trust_message: str
    result_count: int
    cta_primary: str
    cta_secondary: str | None = None
    confidence: float = 0.0
    is_strong: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MarketplacePrioritySearchResult:
    """Result envelope for UI/API rendering."""

    cars: list[Any] = field(default_factory=list)
    services: list[Any] = field(default_factory=list)
    sellers: list[Any] = field(default_factory=list)
    fallback: dict[str, Any] = field(default_factory=dict)
    decisions: list[MarketplaceSearchDecision] = field(default_factory=list)
    query: str = ""
    city: str = ""
    type: str = "all"
    category: str = ""
    service_type: str = ""
    brand: str = ""
    condition: str = ""
    verified: str = ""
    sort: str = "trusted"
    primary_result_type: str = RESULT_REQUEST_FALLBACK
    confidence: float = 0.0
    should_create_request: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decisions"] = [decision.to_dict() for decision in self.decisions]
        return data


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _part_label(interpretation: dict[str, Any]) -> str:
    return _clean(interpretation.get("part_name")) or "потрібної запчастини"


def _vehicle_label(interpretation: dict[str, Any]) -> str:
    parts = [
        interpretation.get("brand"),
        interpretation.get("model") or interpretation.get("generation"),
        interpretation.get("engine"),
        interpretation.get("fuel"),
    ]
    return " ".join(_clean(part) for part in parts if _clean(part)) or "схожих авто"


def _fallback_payload(interpretation: dict[str, Any], raw_query: str) -> dict[str, Any]:
    return {
        "result_type": RESULT_REQUEST_FALLBACK,
        "title": "Не знайшли точний результат?",
        "message": "Створити заявку для продавців? CarPot передасть структурований запит релевантним продавцям.",
        "cta_primary": "Створити заявку",
        "prefill_fields": {
            "raw_query": raw_query,
            "brand": interpretation.get("brand") or "",
            "model": interpretation.get("model") or interpretation.get("generation") or "",
            "part": interpretation.get("part_name") or "",
            "engine": interpretation.get("engine") or "",
            "city": interpretation.get("city") or "",
            "urgency": interpretation.get("urgency") or "normal",
        },
    }


def _decision_confidence(count: int, threshold: int, base: float) -> float:
    if count <= 0:
        return 0.0
    return min(0.95, base + min(count, threshold) * 0.08)


async def run_priority_marketplace_search(
    *,
    interpretation: dict[str, Any],
    raw_query: str,
    search_query: str,
    limit: int = 9,
) -> dict[str, Any]:
    """Run exact → donor → specialization → request CTA without AI DB access.

    The function never skips priority levels for parts requests. Lower-priority
    levels are only queried when the previous level is weak, preserving exact
    inventory precedence while still serving dismantler donor-vehicle logic.
    """

    city = _clean(interpretation.get("city"))
    brand = _clean(interpretation.get("brand"))
    category = _clean(interpretation.get("category"))
    service_type = _clean(interpretation.get("service_type"))
    part_name = _part_label(interpretation)
    vehicle = _vehicle_label(interpretation)
    parsed_confidence = float(interpretation.get("confidence") or 0.0)

    result = MarketplacePrioritySearchResult(
        query=search_query or raw_query,
        city=city,
        type="all",
        category=category if category != "unknown" else "",
        service_type=service_type,
        brand=brand,
        confidence=parsed_confidence,
        fallback=_fallback_payload(interpretation, raw_query),
    )

    exact_matches = await search_exact_part_matches(
        interpretation=interpretation,
        query=search_query or raw_query,
        limit=limit,
    )
    exact_count = len(exact_matches)
    exact_strong = exact_count >= STRONG_EXACT_THRESHOLD
    result.decisions.append(
        MarketplaceSearchDecision(
            step=1,
            result_type=RESULT_EXACT_PART,
            title="Точні збіги по запчастині",
            explanation=(
                f"Шукали {part_name} у явних описах інвентарю продавців за брендом, моделлю, містом "
                "та текстом оголошення."
            ),
            trust_message="Це потенційно точний інвентар продавця, але наявність і стан потрібно підтвердити напряму.",
            result_count=exact_count,
            cta_primary="Відкрити пропозицію",
            cta_secondary="Створити заявку",
            confidence=_decision_confidence(exact_count, STRONG_EXACT_THRESHOLD, 0.55),
            is_strong=exact_strong,
        )
    )
    result.cars.extend(exact_matches)
    if exact_count:
        result.primary_result_type = RESULT_EXACT_PART
        result.should_create_request = not exact_strong

    donor_matches: list[Any] = []
    donor_strong = False
    if not exact_strong:
        donor_matches = await search_donor_vehicle_matches(
            interpretation=interpretation,
            query=search_query or raw_query,
            limit=limit,
        )
        donor_count = len(donor_matches)
        donor_strong = donor_count >= STRONG_DONOR_THRESHOLD
        result.decisions.append(
            MarketplaceSearchDecision(
                step=2,
                result_type=RESULT_DONOR_VEHICLE,
                title="Потенційні donor vehicles",
                explanation=(
                    f"Точної {part_name} недостатньо. Знайдено donor vehicles {vehicle}, "
                    "де ця запчастина може бути доступною після уточнення у розбірника."
                ),
                trust_message="Donor vehicle не означає точну наявність деталі — продавець має підтвердити демонтаж, стан і сумісність.",
                result_count=donor_count,
                cta_primary="Запитати про деталь",
                cta_secondary="Створити заявку",
                confidence=_decision_confidence(donor_count, STRONG_DONOR_THRESHOLD, 0.45),
                is_strong=donor_strong,
            )
        )
        result.cars.extend(donor_matches)
        if donor_count and result.primary_result_type == RESULT_REQUEST_FALLBACK:
            result.primary_result_type = RESULT_DONOR_VEHICLE
        if donor_count:
            result.should_create_request = not donor_strong

    specialization_matches: list[Any] = []
    if not exact_strong and not donor_strong:
        specialization_matches = await search_seller_specialization_matches(
            interpretation=interpretation,
            query=search_query or raw_query,
            limit=8,
        )
        specialization_count = len(specialization_matches)
        specialization_strong = specialization_count >= STRONG_SPECIALIZATION_THRESHOLD
        result.decisions.append(
            MarketplaceSearchDecision(
                step=3,
                result_type=RESULT_SELLER_SPECIALIZATION,
                title="Продавці за спеціалізацією",
                explanation=(
                    f"Знайдено продавців, які спеціалізуються на {vehicle} або напрямку {part_name}. "
                    "Це lead-routing можливість, а не підтверджений складський залишок."
                ),
                trust_message="Спеціалізація базується на профілі продавця, donor vehicles, послугах і описах — деталь потрібно уточнити.",
                result_count=specialization_count,
                cta_primary="Зв'язатися з продавцем",
                cta_secondary="Створити заявку",
                confidence=_decision_confidence(specialization_count, STRONG_SPECIALIZATION_THRESHOLD, 0.35),
                is_strong=specialization_strong,
            )
        )
        result.sellers.extend(specialization_matches)
        if specialization_count and result.primary_result_type == RESULT_REQUEST_FALLBACK:
            result.primary_result_type = RESULT_SELLER_SPECIALIZATION
        if specialization_count:
            result.should_create_request = not specialization_strong

    visible_count = len(result.cars) + len(result.services) + len(result.sellers)
    result.decisions.append(
        MarketplaceSearchDecision(
            step=4,
            result_type=RESULT_REQUEST_FALLBACK,
            title="Заявка продавцям",
            explanation="Якщо marketplace confidence слабкий або потрібне підтвердження наявності, створіть заявку для продавців.",
            trust_message="Заявка повторно використовує buyer request flow і передає продавцям структуровані поля запиту.",
            result_count=1,
            cta_primary="Створити заявку",
            confidence=max(0.25, 1.0 - result.confidence),
            is_strong=visible_count == 0,
        )
    )

    if visible_count == 0:
        result.primary_result_type = RESULT_REQUEST_FALLBACK
        result.should_create_request = True

    return result.to_dict()
