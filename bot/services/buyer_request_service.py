import json
import logging
import re
from dataclasses import dataclass
from html import escape
from typing import Iterable

from fastapi import UploadFile

from bot.database.repositories.buyer_request_repo import create_marketplace_buyer_request_with_routing
from bot.keyboards.seller_leads import seller_lead_notification_kb
from bot.services.buyer_request_safety import inspect_buyer_request_safety
from bot.services.marketplace_routing import build_buyer_request_routing_plan
from bot.services.request_photo_pipeline import RequestPhotoValidationError, prepare_request_photo_assets
from bot.services.telegram_sender import send_message_to_seller


REQUEST_TYPES = {"part", "car", "service", "diagnostics", "tow", "other"}
REQUEST_CATEGORIES = {
    "parts": "Запчастини",
    "cars": "Авто",
    "service": "СТО / ремонт",
    "diagnostics": "Діагностика",
    "tires": "Шини / диски",
    "tow": "Евакуатор",
    "other": "Інше",
}
URGENCY_LEVELS = {"today", "soon", "week", "flexible"}
logger = logging.getLogger(__name__)

CATEGORY_ICONS = {
    "Запчастини": "🔩",
    "Авто": "🚘",
    "СТО / ремонт": "🔧",
    "Діагностика": "🧰",
    "Шини / диски": "🛞",
    "Евакуатор": "🚚",
    "Інше": "📋",
}


@dataclass(slots=True)
class BuyerRequestInput:
    buyer_name: str | None
    buyer_phone: str | None
    buyer_telegram: str | None
    city: str | None
    request_type: str | None
    category: str | None
    brand: str | None
    model: str | None
    vin: str | None
    description: str | None
    urgency: str | None
    photos: Iterable[UploadFile] | None = None


class BuyerRequestValidationError(ValueError):
    pass


def short_text(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:max_length]


def normalize_phone(value: str | None) -> str | None:
    value = short_text(value, 40)
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    if len(digits) == 10 and digits.startswith("0"):
        return f"+38{digits}"
    if len(digits) == 12 and digits.startswith("380"):
        return f"+{digits}"
    if value.startswith("+") and 9 <= len(digits) <= 15:
        return f"+{digits}"
    if 9 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def mask_phone_for_logs(phone: str | None) -> str:
    if not phone:
        return "—"
    digits = re.sub(r"\D+", "", phone)
    if len(digits) <= 4:
        return "***"
    return f"***{digits[-4:]}"


def normalize_telegram(value: str | None) -> str | None:
    value = short_text(value, 80)
    if not value:
        return None
    value = value.replace("https://t.me/", "").replace("http://t.me/", "").strip()
    if value.startswith("@"):
        value = value[1:]
    value = re.sub(r"[^A-Za-z0-9_]", "", value)
    return f"@{value}" if value else None


def buyer_request_title(row: dict | None) -> str:
    if not row:
        return "Заявка CarPot"

    description = short_text(row.get("description"), 120)
    if description:
        for line in description.splitlines():
            line = line.strip()
            if line.startswith("Запит:") or line.startswith("Потрібно:"):
                return line.split(":", 1)[1].strip()[:120] or "Заявка CarPot"

    parts = [
        short_text(row.get("brand"), 80),
        short_text(row.get("model"), 80),
        short_text(row.get("category"), 80),
    ]
    title = " ".join(part for part in parts if part).strip()
    if title:
        return title[:120]

    if description:
        return description[:120]

    return "Заявка CarPot"


def _seller_notification_text(request_row: dict) -> str:
    category = short_text(request_row.get("category"), 80) or "Заявка"
    icon = CATEGORY_ICONS.get(category, "📋")
    title = buyer_request_title(request_row)
    city = short_text(request_row.get("city"), 120) or "—"
    phone = short_text(request_row.get("buyer_phone"), 40) or "—"
    description = short_text(request_row.get("description"), 900) or "Опис не вказано"

    return "\n".join(
        [
            "📥 <b>Нова заявка</b>",
            "",
            f"{escape(icon)} <b>{escape(title)}</b>",
            f"📍 {escape(city)}",
            f"📞 {escape(phone)}",
            "",
            "Опис:",
            escape(description),
        ]
    )


async def _notify_matched_sellers(request_row: dict | None, matches: list[dict]) -> int:
    if not request_row or not matches:
        return 0

    delivered = 0
    request_id = int(request_row["id"])
    text = _seller_notification_text(request_row)
    markup = seller_lead_notification_kb(request_id)

    for match in matches:
        telegram_id = match.get("telegram_id")
        if not telegram_id:
            continue
        try:
            message = await send_message_to_seller(
                int(telegram_id),
                text,
                reply_markup=markup,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning(
                "Immediate seller notification failed request_id=%s seller_id=%s telegram_id=%s: %s",
                request_id,
                match.get("seller_id"),
                telegram_id,
                exc,
            )
            continue
        if message:
            delivered += 1
        else:
            logger.warning(
                "Immediate seller notification was not delivered request_id=%s seller_id=%s telegram_id=%s",
                request_id,
                match.get("seller_id"),
                telegram_id,
            )

    return delivered


def normalize_vin(value: str | None) -> str | None:
    value = short_text(value, 32)
    if not value:
        return None
    value = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{6,17}", value):
        raise BuyerRequestValidationError("VIN має містити 6–17 латинських символів без I, O, Q.")
    return value


def serialize_photo_metadata(photos: Iterable[UploadFile] | None) -> str | None:
    try:
        metadata = prepare_request_photo_assets(photos)
    except RequestPhotoValidationError as exc:
        raise BuyerRequestValidationError(str(exc)) from exc
    return json.dumps(metadata, ensure_ascii=False) if metadata else None


async def submit_marketplace_buyer_request(payload: BuyerRequestInput) -> dict:
    phone = normalize_phone(payload.buyer_phone)
    if not phone:
        raise BuyerRequestValidationError("Вкажіть коректний телефон.")

    city = short_text(payload.city, 120)
    if not city or len(city) < 2:
        raise BuyerRequestValidationError("Вкажіть місто, де актуальна заявка.")

    description = short_text(payload.description, 1400)
    if not description or len(description) < 12:
        raise BuyerRequestValidationError("Опишіть потребу детальніше — мінімум 12 символів.")

    request_type = short_text(payload.request_type, 40) or "part"
    if request_type not in REQUEST_TYPES:
        request_type = "other"

    category_key = short_text(payload.category, 60) or "parts"
    category = REQUEST_CATEGORIES.get(category_key, short_text(payload.category, 80) or "Інше")

    urgency = short_text(payload.urgency, 24) or "soon"
    if urgency not in URGENCY_LEVELS:
        urgency = "soon"

    vin = normalize_vin(payload.vin)
    photos = serialize_photo_metadata(payload.photos)

    safety = inspect_buyer_request_safety(
        phone=phone,
        city=city,
        request_type=request_type,
        category=category,
        description=description,
        vin=vin,
    )

    brand = short_text(payload.brand, 80)
    model = short_text(payload.model, 80)
    parsed_payload = {
        "category": category,
        "request_type": request_type,
        "brand": brand,
        "model": model,
        "city": city,
        "urgency": urgency,
        "vin_present": bool(vin),
        "photo_count": len(json.loads(photos)) if photos else 0,
    }

    creation = await create_marketplace_buyer_request_with_routing(
        buyer_name=short_text(payload.buyer_name, 120),
        buyer_phone=phone,
        buyer_telegram=normalize_telegram(payload.buyer_telegram),
        city=city,
        request_type=request_type,
        category=category,
        brand=brand,
        model=model,
        vin=vin,
        description=description,
        photos=photos,
        urgency=urgency,
        status="pending",
        request_fingerprint=safety.fingerprint,
        normalized_phone=safety.normalized_phone,
        safety_status="suspicious" if safety.suspicious else "clear",
        safety_flags=safety.to_dict(),
        source="buyer_web",
        parsed_payload=parsed_payload,
        seller_limit=20,
    )
    row = creation.get("request")
    matches = [dict(match) for match in creation.get("matches", [])]

    routing_plan = build_buyer_request_routing_plan(
        city=city,
        category=category,
        request_type=request_type,
        brand=brand,
        model=model,
        urgency=urgency,
    )
    routing_plan["matched_sellers"] = len(matches)
    routing_plan["notification_events_created"] = creation.get("notification_events_created", 0)
    routing_plan["matches"] = [
        {
            "seller_id": match.get("seller_id"),
            "telegram_id": match.get("telegram_id"),
            "score": match.get("score"),
            "reasons": list(match.get("reasons") or []),
            "city": match.get("city"),
            "shop_name": match.get("shop_name") or match.get("name"),
            "is_verified": bool(match.get("is_verified")),
        }
        for match in matches
    ]

    logger.info(
        "Buyer request created request_id=%s city=%s category=%s phone=%s matched_sellers=%s notification_events=%s",
        row["id"] if row else None,
        city,
        category,
        mask_phone_for_logs(phone),
        len(matches),
        creation.get("notification_events_created", 0),
    )

    try:
        delivered_notifications = await _notify_matched_sellers(dict(row) if row else None, matches)
    except Exception as exc:
        delivered_notifications = 0
        logger.warning(
            "Immediate seller notification delivery skipped after request creation request_id=%s: %s",
            row["id"] if row else None,
            exc,
        )

    return {
        "request": dict(row) if row else None,
        "routing_plan": routing_plan,
        "matched_sellers": len(matches),
        "notification_events_created": creation.get("notification_events_created", 0),
        "telegram_notifications_delivered": delivered_notifications,
        "safety": safety.to_dict(),
    }
