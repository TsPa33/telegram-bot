from dataclasses import dataclass
from decimal import Decimal

from bot.database.repositories.buyer_offer_repo import (
    accept_buyer_offer,
    get_buyer_offer_detail,
    get_buyer_request_for_offer_view,
    list_buyer_offer_cards,
)
from bot.services.seller_trust import build_seller_trust_indicators


@dataclass(slots=True)
class BuyerOfferAcceptanceResult:
    accepted: bool
    request_id: int
    offer_id: int
    match: dict | None = None
    notification_event: dict | None = None


def _public_seller_name(offer: dict) -> str:
    return offer.get("shop_name") or offer.get("seller_name") or "Продавець CarPot"


def _telegram_url(username: str | None) -> str | None:
    if not username:
        return None
    normalized = str(username).strip().lstrip("@")
    return f"https://t.me/{normalized}" if normalized else None


def _format_response_speed(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    if seconds <= 15 * 60:
        return "до 15 хв"
    if seconds <= 60 * 60:
        return "до 1 год"
    if seconds <= 6 * 60 * 60:
        return "до 6 год"
    hours = max(1, round(seconds / 3600))
    return f"~{hours} год"


def _format_price(price: Decimal | int | float | str | None) -> str:
    if price in (None, ""):
        return "За домовленістю"
    try:
        value = Decimal(str(price))
    except Exception:
        return str(price)
    if value == value.to_integral_value():
        return f"{int(value):,}".replace(",", " ") + " грн"
    return f"{value:,.2f}".replace(",", " ") + " грн"


def build_offer_view_model(offer: dict, *, accepted_offer_id: int | None) -> dict:
    is_accepted = offer.get("status") == "accepted" or offer.get("is_selected_match") or offer.get("id") == accepted_offer_id
    contact_unlocked = bool(is_accepted)
    response_speed = offer.get("avg_response_seconds") or offer.get("last_response_seconds")
    normalized = dict(offer)
    normalized.update(
        {
            "seller_display_name": _public_seller_name(offer),
            "seller_initial": _public_seller_name(offer)[:1].upper(),
            "price_label": _format_price(offer.get("price_offer")),
            "trust_indicators": build_seller_trust_indicators(offer),
            "telegram_url": _telegram_url(offer.get("seller_username")) if contact_unlocked else None,
            "website_url": offer.get("seller_website") if contact_unlocked else None,
            "phone_visible": offer.get("seller_phone") if contact_unlocked else None,
            "contact_unlocked": contact_unlocked,
            "is_accepted": is_accepted,
            "is_rejected": offer.get("status") == "rejected",
            "response_speed_label": _format_response_speed(response_speed),
        }
    )
    return normalized


def build_request_view_model(request_row: dict, offers: list[dict]) -> dict:
    accepted_offer_id = request_row.get("accepted_offer_id")
    normalized_offers = [build_offer_view_model(dict(offer), accepted_offer_id=accepted_offer_id) for offer in offers]
    accepted_offer = next((offer for offer in normalized_offers if offer["is_accepted"]), None)
    title = " ".join(part for part in [request_row.get("brand"), request_row.get("model"), request_row.get("category")] if part).strip()
    if not title:
        title = request_row.get("request_type") or "Заявка покупця"
    request_model = dict(request_row)
    request_model.update(
        {
            "title": title,
            "is_matched": request_row.get("marketplace_status") == "matched" or bool(accepted_offer),
            "accepted_offer": accepted_offer,
            "offers": normalized_offers,
            "pending_offers_count": len([offer for offer in normalized_offers if offer.get("status") == "pending"]),
        }
    )
    return request_model


async def get_buyer_offer_comparison(request_id: int) -> dict | None:
    request_row = await get_buyer_request_for_offer_view(request_id)
    if not request_row:
        return None
    offers = await list_buyer_offer_cards(request_id)
    return build_request_view_model(dict(request_row), [dict(offer) for offer in offers])


async def accept_offer_for_buyer(request_id: int, offer_id: int) -> BuyerOfferAcceptanceResult:
    offer = await get_buyer_offer_detail(request_id, offer_id)
    if not offer:
        return BuyerOfferAcceptanceResult(False, request_id, offer_id)
    result = await accept_buyer_offer(request_id, offer_id, reject_other_offers=True)
    if not result:
        return BuyerOfferAcceptanceResult(False, request_id, offer_id)
    return BuyerOfferAcceptanceResult(
        True,
        request_id,
        offer_id,
        match=result.get("match"),
        notification_event=result.get("notification_event"),
    )


def build_seller_offer_accepted_notification(*, request_model: dict, offer: dict) -> dict:
    title = request_model.get("title") or request_model.get("category") or "Заявка CarPot"
    city = request_model.get("city") or "Україна"
    text = f"🎉 Вашу пропозицію обрали\n\n{title}\n{city}\n\nПокупець обрав вашу пропозицію."
    return {
        "event_type": "seller_offer_accepted",
        "seller_id": offer.get("seller_id"),
        "request_id": request_model.get("id"),
        "offer_id": offer.get("id"),
        "telegram_text": text,
    }
