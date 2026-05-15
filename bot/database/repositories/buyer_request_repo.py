import json
from decimal import Decimal

from bot.database.base import fetch, fetchrow


BUYER_REQUEST_STATUSES = {"pending", "active", "matched", "closed"}
BUYER_REQUEST_OFFER_STATUSES = {"pending", "accepted", "rejected"}
LEGACY_REQUEST_STATUS = "new"


def _validate(value: str, allowed: set[str], message: str) -> None:
    if value not in allowed:
        raise ValueError(message)


async def create_marketplace_buyer_request(
    *,
    buyer_name: str | None,
    buyer_phone: str,
    buyer_telegram: str | None,
    city: str,
    request_type: str,
    category: str,
    brand: str | None,
    model: str | None,
    vin: str | None,
    description: str,
    photos: str | None,
    urgency: str | None,
    status: str = "pending",
    request_fingerprint: str | None = None,
    normalized_phone: str | None = None,
    safety_status: str = "clear",
    safety_flags: dict | None = None,
):
    _validate(status, BUYER_REQUEST_STATUSES, "Invalid buyer request status")

    return await fetchrow(
        """
        INSERT INTO buyer_requests (
            telegram_id,
            request_type,
            entity_type,
            entity_ref,
            status,
            message,
            buyer_name,
            buyer_phone,
            buyer_telegram,
            city,
            category,
            brand,
            model,
            vin,
            description,
            photos,
            urgency,
            marketplace_status,
            request_fingerprint,
            normalized_phone,
            safety_status,
            safety_flags
        )
        VALUES (
            0,
            $1,
            'marketplace_request',
            'web-marketplace',
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8,
            $9,
            $10,
            $11,
            $12,
            $13::jsonb,
            $14,
            $15,
            $16,
            $17,
            $18,
            COALESCE($19::jsonb, '{}'::jsonb)
        )
        RETURNING id, buyer_name, buyer_phone, buyer_telegram, city, request_type,
                  category, brand, model, vin, description, photos, urgency,
                  marketplace_status, request_fingerprint, normalized_phone,
                  safety_status, safety_flags, created_at
        """,
        request_type,
        LEGACY_REQUEST_STATUS,
        description,
        buyer_name,
        buyer_phone,
        buyer_telegram,
        city,
        category,
        brand,
        model,
        vin,
        description,
        photos,
        urgency,
        status,
        request_fingerprint,
        normalized_phone,
        safety_status,
        json.dumps(safety_flags or {}, ensure_ascii=False),
    )


async def list_active_marketplace_requests(
    *,
    city: str | None = None,
    category: str | None = None,
    limit: int = 20,
):
    normalized_limit = max(1, min(int(limit or 20), 50))
    return await fetch(
        """
        SELECT id, buyer_name, city, request_type, category, brand, model, vin,
               description, urgency, marketplace_status, created_at
        FROM buyer_requests
        WHERE entity_type = 'marketplace_request'
          AND marketplace_status IN ('pending', 'active')
          AND ($1::text IS NULL OR city ILIKE $1)
          AND ($2::text IS NULL OR category ILIKE $2 OR request_type ILIKE $2)
        ORDER BY created_at DESC, id DESC
        LIMIT $3
        """,
        f"%{city.strip()}%" if city else None,
        f"%{category.strip()}%" if category else None,
        normalized_limit,
    )


async def create_buyer_request_offer(
    *,
    request_id: int,
    seller_id: int,
    message: str,
    price_offer: Decimal | None = None,
    availability_note: str | None = None,
    status: str = "pending",
):
    _validate(status, BUYER_REQUEST_OFFER_STATUSES, "Invalid buyer request offer status")

    return await fetchrow(
        """
        INSERT INTO buyer_request_offers (request_id, seller_id, message, price_offer, availability_note, status)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, request_id, seller_id, message, price_offer, availability_note, status, created_at
        """,
        request_id,
        seller_id,
        message,
        price_offer,
        availability_note,
        status,
    )


async def list_request_offers(request_id: int):
    return await fetch(
        """
        SELECT bro.id, bro.request_id, bro.seller_id, bro.message, bro.price_offer,
               bro.availability_note, bro.status, bro.created_at,
               s.shop_name, s.name AS seller_name, s.username AS seller_username,
               s.phone AS seller_phone, s.city AS seller_city, s.is_verified
        FROM buyer_request_offers bro
        JOIN sellers s ON s.id = bro.seller_id
        WHERE bro.request_id = $1
        ORDER BY bro.created_at DESC, bro.id DESC
        """,
        request_id,
    )
