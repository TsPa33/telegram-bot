from dataclasses import dataclass, asdict


@dataclass(slots=True)
class BuyerRequestRoutingPlan:
    city: str
    category: str
    request_type: str
    specialization_tags: list[str]
    priority: str
    paid_lead_ready: bool
    telegram_preview: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_buyer_request_routing_plan(
    *,
    city: str,
    category: str,
    request_type: str,
    brand: str | None = None,
    model: str | None = None,
    urgency: str | None = None,
) -> dict:
    tags = [category, request_type]
    if brand:
        tags.append(brand)
    if model:
        tags.append(model)

    priority = "high" if urgency == "today" else "normal"
    title = " ".join(part for part in [brand, model, category] if part).strip() or category
    preview = f"🔥 Нова заявка\n{title}\n{city}\n\n[Запропонувати] [Пропустити]"

    return BuyerRequestRoutingPlan(
        city=city,
        category=category,
        request_type=request_type,
        specialization_tags=tags,
        priority=priority,
        paid_lead_ready=True,
        telegram_preview=preview,
    ).to_dict()
