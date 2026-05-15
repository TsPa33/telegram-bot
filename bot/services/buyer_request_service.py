import json
import re
from dataclasses import dataclass
from typing import Iterable

from fastapi import UploadFile

from bot.database.repositories.buyer_request_repo import create_marketplace_buyer_request
from bot.services.buyer_request_safety import inspect_buyer_request_safety
from bot.services.marketplace_routing import build_buyer_request_routing_plan
from bot.services.request_photo_pipeline import RequestPhotoValidationError, prepare_request_photo_assets


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


def normalize_telegram(value: str | None) -> str | None:
    value = short_text(value, 80)
    if not value:
        return None
    value = value.replace("https://t.me/", "").replace("http://t.me/", "").strip()
    if value.startswith("@"):
        value = value[1:]
    value = re.sub(r"[^A-Za-z0-9_]", "", value)
    return f"@{value}" if value else None


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

    row = await create_marketplace_buyer_request(
        buyer_name=short_text(payload.buyer_name, 120),
        buyer_phone=phone,
        buyer_telegram=normalize_telegram(payload.buyer_telegram),
        city=city,
        request_type=request_type,
        category=category,
        brand=short_text(payload.brand, 80),
        model=short_text(payload.model, 80),
        vin=vin,
        description=description,
        photos=photos,
        urgency=urgency,
        status="pending",
        request_fingerprint=safety.fingerprint,
        normalized_phone=safety.normalized_phone,
        safety_status="suspicious" if safety.suspicious else "clear",
        safety_flags=safety.to_dict(),
    )

    routing_plan = build_buyer_request_routing_plan(
        city=city,
        category=category,
        request_type=request_type,
        brand=short_text(payload.brand, 80),
        model=short_text(payload.model, 80),
        urgency=urgency,
    )

    return {"request": dict(row) if row else None, "routing_plan": routing_plan, "safety": safety.to_dict()}
