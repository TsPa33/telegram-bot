from dataclasses import dataclass, asdict


@dataclass(slots=True)
class LeadScoreBreakdown:
    city_score: int = 0
    specialization_score: int = 0
    seller_activity_score: int = 0
    verified_score: int = 0
    premium_score: int = 0
    response_speed_score: int = 0

    @property
    def total(self) -> int:
        return (
            self.city_score
            + self.specialization_score
            + self.seller_activity_score
            + self.verified_score
            + self.premium_score
            + self.response_speed_score
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["total"] = self.total
        return payload


class LeadScoringService:
    """Deterministic foundation for future marketplace lead routing."""

    def score_city(self, buyer_city: str | None, seller_city: str | None) -> int:
        if not buyer_city or not seller_city:
            return 0
        return 35 if buyer_city.strip().lower() in seller_city.strip().lower() or seller_city.strip().lower() in buyer_city.strip().lower() else 0

    def score_specialization(self, request_terms: list[str], seller_tags: list[str]) -> int:
        normalized_terms = [term.strip().lower() for term in request_terms if term]
        normalized_tags = [tag.strip().lower() for tag in seller_tags if tag]
        if not normalized_terms or not normalized_tags:
            return 0
        for term in normalized_terms:
            if any(term in tag or tag in term for tag in normalized_tags):
                return 30
        return 0

    def score_seller_activity(self, marketplace_activity: int | None) -> int:
        activity = int(marketplace_activity or 0)
        if activity >= 10:
            return 10
        if activity >= 3:
            return 7
        if activity > 0:
            return 4
        return 0

    def score_verified(self, is_verified: bool | None) -> int:
        return 10 if is_verified else 0

    def score_premium(self, has_site: bool | None, crm_enabled: bool | None) -> int:
        return 8 if has_site or crm_enabled else 0

    def score_response_speed(self, avg_response_seconds: int | None) -> int:
        if avg_response_seconds is None:
            return 0
        if avg_response_seconds <= 15 * 60:
            return 7
        if avg_response_seconds <= 60 * 60:
            return 5
        if avg_response_seconds <= 6 * 60 * 60:
            return 2
        return 0

    def score(self, *, buyer_city: str | None, seller_city: str | None, request_terms: list[str], seller_tags: list[str], marketplace_activity: int | None, is_verified: bool | None, has_site: bool | None, crm_enabled: bool | None, avg_response_seconds: int | None = None) -> LeadScoreBreakdown:
        return LeadScoreBreakdown(
            city_score=self.score_city(buyer_city, seller_city),
            specialization_score=self.score_specialization(request_terms, seller_tags),
            seller_activity_score=self.score_seller_activity(marketplace_activity),
            verified_score=self.score_verified(is_verified),
            premium_score=self.score_premium(has_site, crm_enabled),
            response_speed_score=self.score_response_speed(avg_response_seconds),
        )
