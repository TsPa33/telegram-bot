import json
from decimal import Decimal

from bot.database.base import fetch, fetchrow, transaction


BUYER_REQUEST_STATUSES = {"pending", "active", "matched", "closed"}
BUYER_REQUEST_OFFER_STATUSES = {"pending", "accepted", "rejected"}
LEGACY_REQUEST_STATUS = "new"
MAX_ROUTED_SELLERS = 20
BUYER_REQUEST_CREATED_EVENT = "buyer_request_created"


def _validate(value: str, allowed: set[str], message: str) -> None:
    if value not in allowed:
        raise ValueError(message)


def _json(value: dict | list | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


async def _insert_marketplace_buyer_request(
    executor,
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
    source: str = "buyer_web",
    parsed_payload: dict | None = None,
):
    _validate(status, BUYER_REQUEST_STATUSES, "Invalid buyer request status")

    return await executor.fetchrow(
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
            raw_query,
            photos,
            urgency,
            marketplace_status,
            request_fingerprint,
            normalized_phone,
            safety_status,
            safety_flags,
            source,
            parsed_payload
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
            $12,
            $13::jsonb,
            $14,
            $15,
            $16,
            $17,
            $18,
            COALESCE($19::jsonb, '{}'::jsonb),
            $20,
            COALESCE($21::jsonb, '{}'::jsonb)
        )
        RETURNING id, buyer_name, buyer_phone, buyer_telegram, city, request_type,
                  category, brand, model, vin, description, raw_query, photos, urgency,
                  marketplace_status, request_fingerprint, normalized_phone,
                  safety_status, safety_flags, source, parsed_payload, created_at
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
        _json(safety_flags),
        source,
        _json(parsed_payload),
    )


async def _find_matching_sellers_for_request(
    executor,
    *,
    city: str | None,
    category: str | None,
    request_type: str | None,
    brand: str | None,
    model: str | None,
    description: str | None,
    urgency: str | None,
    limit: int = MAX_ROUTED_SELLERS,
):
    normalized_limit = max(1, min(int(limit or MAX_ROUTED_SELLERS), MAX_ROUTED_SELLERS))
    return await executor.fetch(
        """
        WITH seller_activity AS (
            SELECT s.id AS seller_id,
                   COUNT(DISTINCT sc.id)::int AS cars_count,
                   COUNT(DISTINCT sv.id)::int AS services_count
            FROM sellers s
            LEFT JOIN seller_cars sc ON sc.seller_id = s.id AND COALESCE(sc.status, 1) = 1
            LEFT JOIN services sv ON sv.seller_id = s.id
            GROUP BY s.id
        ), seller_signals AS (
            SELECT s.id AS seller_id,
                   s.telegram_id,
                   s.city,
                   s.shop_name,
                   s.name,
                   COALESCE(s.is_verified, FALSE) AS is_verified,
                   COALESCE(s.has_site, FALSE) AS has_site,
                   COALESCE(s.crm_enabled, FALSE) AS crm_enabled,
                   COALESCE(sa.cars_count, 0) AS cars_count,
                   COALESCE(sa.services_count, 0) AS services_count,
                   EXISTS (
                       SELECT 1
                       FROM unnest(COALESCE(s.specialization_tags, ARRAY[]::text[])) tag(value)
                       WHERE tag.value IS NOT NULL
                         AND (
                              LOWER(COALESCE($2, '')) LIKE '%' || LOWER(tag.value) || '%'
                           OR LOWER(COALESCE($3, '')) LIKE '%' || LOWER(tag.value) || '%'
                           OR LOWER(COALESCE($4, '')) LIKE '%' || LOWER(tag.value) || '%'
                           OR LOWER(COALESCE($5, '')) LIKE '%' || LOWER(tag.value) || '%'
                           OR LOWER(COALESCE($6, '')) LIKE '%' || LOWER(tag.value) || '%'
                         )
                   ) AS specialization_match,
                   EXISTS (
                       SELECT 1
                       FROM seller_cars sc
                       JOIN models m ON m.id = sc.model_id
                       JOIN brands b ON b.id = m.brand_id
                       WHERE sc.seller_id = s.id
                         AND COALESCE(sc.status, 1) = 1
                         AND (
                              (COALESCE($4, '') <> '' AND LOWER(b.name) = LOWER($4))
                           OR (COALESCE($5, '') <> '' AND LOWER(m.name) = LOWER($5))
                           OR (COALESCE($6, '') <> '' AND LOWER(COALESCE(sc.description, '')) LIKE '%' || LOWER($6) || '%')
                           OR (COALESCE($6, '') <> '' AND LOWER(COALESCE(sc.compatibility_notes, '')) LIKE '%' || LOWER($6) || '%')
                         )
                   ) AS car_match,
                   EXISTS (
                       SELECT 1
                       FROM services sv
                       WHERE sv.seller_id = s.id
                         AND (
                              LOWER(COALESCE(sv.category, '')) LIKE '%' || LOWER(COALESCE($2, '')) || '%'
                           OR LOWER(COALESCE(sv.title, '')) LIKE '%' || LOWER(COALESCE($2, '')) || '%'
                           OR LOWER(COALESCE(sv.title, '')) LIKE '%' || LOWER(COALESCE($3, '')) || '%'
                           OR (COALESCE($6, '') <> '' AND LOWER(COALESCE(sv.description, '')) LIKE '%' || LOWER($6) || '%')
                         )
                   ) AS service_match
            FROM sellers s
            LEFT JOIN seller_activity sa ON sa.seller_id = s.id
            WHERE s.telegram_id IS NOT NULL
        ), scored AS (
            SELECT *,
                   (CASE WHEN COALESCE($1, '') <> '' AND city IS NOT NULL AND LOWER(city) = LOWER($1) THEN 30 ELSE 0 END) +
                   (CASE WHEN specialization_match THEN 20 ELSE 0 END) +
                   (CASE WHEN service_match THEN 20 ELSE 0 END) +
                   (CASE WHEN car_match THEN 20 ELSE 0 END) +
                   (CASE WHEN COALESCE($4, '') <> '' AND specialization_match THEN 10 ELSE 0 END) +
                   (CASE WHEN COALESCE($5, '') <> '' AND car_match THEN 10 ELSE 0 END) +
                   (CASE WHEN $7 = 'today' THEN 5 ELSE 0 END) +
                   (CASE WHEN is_verified THEN 5 ELSE 0 END) +
                   (CASE WHEN has_site OR crm_enabled THEN 5 ELSE 0 END) +
                   (CASE WHEN cars_count > 0 OR services_count > 0 THEN 5 ELSE 0 END) AS score,
                   ARRAY_REMOVE(ARRAY[
                       CASE WHEN COALESCE($1, '') <> '' AND city IS NOT NULL AND LOWER(city) = LOWER($1) THEN 'city' END,
                       CASE WHEN specialization_match THEN 'specialization_tags' END,
                       CASE WHEN service_match THEN 'services' END,
                       CASE WHEN car_match THEN 'seller_cars' END,
                       CASE WHEN is_verified THEN 'verified' END,
                       CASE WHEN has_site OR crm_enabled THEN 'active_tools' END,
                       CASE WHEN cars_count > 0 OR services_count > 0 THEN 'active_inventory' END
                   ], NULL) AS reasons
            FROM seller_signals
        )
        SELECT seller_id, telegram_id, score, reasons, city, shop_name, name, is_verified
        FROM scored
        WHERE score > 0
        ORDER BY score DESC, is_verified DESC, (cars_count + services_count) DESC, seller_id DESC
        LIMIT $8
        """,
        city,
        category,
        request_type,
        brand,
        model,
        description,
        urgency,
        normalized_limit,
    )


async def _create_buyer_request_notification_events(executor, *, request_row, matches) -> int:
    created = 0
    for match in matches:
        payload = {
            "request_id": request_row["id"],
            "seller_id": match["seller_id"],
            "score": match["score"],
            "reasons": list(match["reasons"] or []),
            "city": match["city"],
            "shop_name": match["shop_name"] or match["name"],
            "is_verified": bool(match["is_verified"]),
            "category": request_row["category"],
            "request_type": request_row["request_type"],
            "brand": request_row["brand"],
            "model": request_row["model"],
            "urgency": request_row["urgency"],
        }
        inserted = await executor.fetchrow(
            """
            INSERT INTO marketplace_notification_events (
                event_type, request_id, seller_id, payload, status, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4::jsonb, 'pending', NOW(), NOW())
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            BUYER_REQUEST_CREATED_EVENT,
            request_row["id"],
            match["seller_id"],
            json.dumps(payload, ensure_ascii=False),
        )
        if inserted:
            created += 1
    return created


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
    source: str = "buyer_web",
    parsed_payload: dict | None = None,
):
    class _BaseExecutor:
        fetchrow = staticmethod(fetchrow)

    return await _insert_marketplace_buyer_request(
        _BaseExecutor,
        buyer_name=buyer_name,
        buyer_phone=buyer_phone,
        buyer_telegram=buyer_telegram,
        city=city,
        request_type=request_type,
        category=category,
        brand=brand,
        model=model,
        vin=vin,
        description=description,
        photos=photos,
        urgency=urgency,
        status=status,
        request_fingerprint=request_fingerprint,
        normalized_phone=normalized_phone,
        safety_status=safety_status,
        safety_flags=safety_flags,
        source=source,
        parsed_payload=parsed_payload,
    )


async def create_marketplace_buyer_request_with_routing(
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
    source: str = "buyer_web",
    parsed_payload: dict | None = None,
    seller_limit: int = MAX_ROUTED_SELLERS,
) -> dict:
    async with transaction() as conn:
        request_row = await _insert_marketplace_buyer_request(
            conn,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            buyer_telegram=buyer_telegram,
            city=city,
            request_type=request_type,
            category=category,
            brand=brand,
            model=model,
            vin=vin,
            description=description,
            photos=photos,
            urgency=urgency,
            status=status,
            request_fingerprint=request_fingerprint,
            normalized_phone=normalized_phone,
            safety_status=safety_status,
            safety_flags=safety_flags,
            source=source,
            parsed_payload=parsed_payload,
        )
        matches = await _find_matching_sellers_for_request(
            conn,
            city=city,
            category=category,
            request_type=request_type,
            brand=brand,
            model=model,
            description=description,
            urgency=urgency,
            limit=seller_limit,
        )
        event_count = await _create_buyer_request_notification_events(
            conn,
            request_row=request_row,
            matches=matches,
        )
        return {
            "request": request_row,
            "matches": matches,
            "notification_events_created": event_count,
        }


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
               description, raw_query, urgency, marketplace_status, source,
               parsed_payload, created_at
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
