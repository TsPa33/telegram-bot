import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import escape

from bot.database.repositories.seller_lead_repo import (
    create_seller_offer,
    ensure_buyer_offer_created_event,
    get_buyer_offer_notification_context,
    get_seller_offer_access_context,
    mark_marketplace_notification_event,
    mark_seller_lead_action,
    touch_request_matched,
)
from bot.keyboards.buyer_requests_inline import buyer_offer_created_notification_kb
from bot.services.telegram_sender import send_message_to_buyer

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SellerOfferResult:
    ok: bool
    offer: dict | None = None
    error: str | None = None
    notification_status: str | None = None

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "offer": self.offer,
            "error": self.error,
            "notification_status": self.notification_status,
        }


def _lead_title(context: dict) -> str:
    description = (context.get("description") or "").strip()
    for line in description.splitlines():
        line = line.strip()
        if line.startswith("Запит:") or line.startswith("Потрібно:"):
            title = line.split(":", 1)[1].strip()
            if title:
                return title[:120]
    return " ".join(
        part for part in [context.get("brand"), context.get("model"), context.get("category")] if part
    ).strip() or context.get("category") or "Автомобільна заявка"


def _format_price_offer(value) -> str:
    if value in (None, ""):
        return "договірна"
    text = str(value).rstrip("0").rstrip(".")
    return f"{text} грн" if text else "договірна"


def _format_buyer_offer_notification(context: dict) -> str:
    seller_name = escape(context.get("shop_name") or context.get("seller_name") or "Продавець CarPot")
    lines = [
        "🆕 <b>Нова відповідь на вашу заявку</b>",
        "",
        f"<b>{escape(_lead_title(context))}</b>",
        f"🏪 {seller_name}",
        f"💰 {escape(_format_price_offer(context.get('price_offer')))}",
    ]
    seller_city = (context.get("seller_city") or "").strip()
    if seller_city:
        lines.append(f"📍 {escape(seller_city)}")

    message = (context.get("message") or "").strip()
    if message:
        lines.extend(["", "Коментар:", escape(message[:700])])
    return "\n".join(lines)


def _normalize_price(price_text: str | None) -> tuple[Decimal | None, str | None]:
    text = (price_text or "").strip()
    if not text:
        return None, None
    if len(text) > 80:
        return None, "Ціна має бути не довша за 80 символів."

    normalized = text.lower().replace("ʼ", "'").replace("’", "'")
    if normalized in {"договірна", "договорная", "за домовленістю", "за домовленностью"}:
        return None, None

    numeric = text.lower().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if numeric.endswith("грн"):
        numeric = numeric[:-3].strip()
    try:
        value = Decimal(numeric)
    except (InvalidOperation, ValueError):
        return None, "Вкажіть ціну цифрами або напишіть “договірна”."
    if value < 0:
        return None, "Ціна не може бути відʼємною."
    return value, None


def _validate_message(message: str | None) -> tuple[str | None, str | None]:
    text = (message or "").strip()
    if not text:
        return None, "Додайте коментар до пропозиції."
    if len(text) > 1000:
        return None, "Коментар має бути не довший за 1000 символів."
    return text, None


async def _notify_buyer_about_offer(*, request_id: int, seller_id: int, offer: dict) -> str:
    offer_id = offer.get("id") if offer else None
    if not offer_id:
        return "skipped"

    event = await ensure_buyer_offer_created_event(
        request_id=request_id,
        seller_id=seller_id,
        offer_id=int(offer_id),
    )
    if event.get("already_exists"):
        logger.info(
            "Buyer offer-created notification already recorded request_id=%s offer_id=%s seller_id=%s event_id=%s",
            request_id,
            offer_id,
            seller_id,
            event.get("id"),
        )
        return "already_recorded"

    context_row = await get_buyer_offer_notification_context(
        request_id=request_id,
        seller_id=seller_id,
        offer_id=int(offer_id),
    )
    context = dict(context_row) if context_row else {}
    buyer_telegram_id = context.get("buyer_telegram_id")
    if not buyer_telegram_id:
        logger.warning(
            "Buyer telegram_id missing for CRM offer notification request_id=%s offer_id=%s seller_id=%s",
            request_id,
            offer_id,
            seller_id,
        )
        await mark_marketplace_notification_event(event.get("id"), status="failed")
        return "failed"

    sent = await send_message_to_buyer(
        int(buyer_telegram_id),
        _format_buyer_offer_notification(context),
        parse_mode="HTML",
        reply_markup=buyer_offer_created_notification_kb(request_id),
    )
    if sent:
        await mark_marketplace_notification_event(event.get("id"), status="sent")
        logger.info(
            "Buyer notified about CRM seller offer buyer_telegram_id=%s request_id=%s offer_id=%s",
            buyer_telegram_id,
            request_id,
            offer_id,
        )
        return "sent"

    await mark_marketplace_notification_event(event.get("id"), status="failed")
    logger.warning(
        "Telegram send failure CRM buyer offer notification buyer_telegram_id=%s request_id=%s offer_id=%s",
        buyer_telegram_id,
        request_id,
        offer_id,
    )
    return "failed"


async def submit_seller_offer(
    *,
    seller_id: int,
    request_id: int,
    price_text: str | None,
    message: str | None,
    source: str = "crm",
) -> dict:
    price_offer, price_error = _normalize_price(price_text)
    if price_error:
        return SellerOfferResult(ok=False, error=price_error).as_dict()

    comment, message_error = _validate_message(message)
    if message_error:
        return SellerOfferResult(ok=False, error=message_error).as_dict()

    access = await get_seller_offer_access_context(seller_id=seller_id, request_id=request_id)
    if not access:
        return SellerOfferResult(ok=False, error="Заявка недоступна для цього продавця.").as_dict()

    selected_seller_id = access.get("selected_seller_id")
    if selected_seller_id and int(selected_seller_id) != int(seller_id):
        return SellerOfferResult(ok=False, error="Покупець уже обрав іншого продавця.").as_dict()

    has_existing_offer = bool(access.get("offer_id"))
    if (access.get("has_declined") or access.get("has_skipped")) and not has_existing_offer:
        return SellerOfferResult(ok=False, error="Цю заявку вже відхилено або пропущено.").as_dict()

    offer = await create_seller_offer(
        request_id=request_id,
        seller_id=seller_id,
        message=comment,
        price_offer=price_offer,
        availability_note="Готовий обговорити",
        status="pending",
    )
    offer_dict = dict(offer) if offer else None

    await mark_seller_lead_action(
        seller_id=seller_id,
        request_id=request_id,
        action="offered",
        metadata={"source": source},
    )
    await touch_request_matched(request_id)

    notification_status = "skipped"
    try:
        notification_status = await _notify_buyer_about_offer(
            request_id=request_id,
            seller_id=seller_id,
            offer=offer_dict or {},
        )
    except Exception as exc:
        logger.warning(
            "Buyer offer notification failed without blocking CRM offer request_id=%s seller_id=%s offer_id=%s: %s",
            request_id,
            seller_id,
            offer_dict.get("id") if offer_dict else None,
            exc,
        )
        notification_status = "failed"

    logger.info(
        "Seller offer submitted source=%s seller_id=%s request_id=%s offer_id=%s notification_status=%s",
        source,
        seller_id,
        request_id,
        offer_dict.get("id") if offer_dict else None,
        notification_status,
    )
    return SellerOfferResult(ok=True, offer=offer_dict, notification_status=notification_status).as_dict()


async def submit_seller_offer_from_crm(
    *,
    seller_id: int,
    request_id: int,
    price_text: str | None,
    message: str | None,
) -> dict:
    return await submit_seller_offer(
        seller_id=seller_id,
        request_id=request_id,
        price_text=price_text,
        message=message,
        source="crm",
    )
