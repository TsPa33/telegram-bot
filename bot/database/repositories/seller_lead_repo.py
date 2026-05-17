import json
import logging
from decimal import Decimal

from bot.database.base import execute, fetch, fetchrow


SELLER_LEAD_ACTIONS = {"viewed", "skipped", "offered", "declined"}
BUYER_REQUEST_OFFER_STATUSES = {"pending", "accepted", "rejected"}
logger = logging.getLogger(__name__)


def _validate(value: str, allowed: set[str], message: str) -> None:
    if value not in allowed:
        raise ValueError(message)


async def get_seller_marketplace_profile(telegram_id: int):
    return await fetchrow(
        """
        SELECT id, telegram_id, username, shop_name, name, phone, website, city,
               description, photo_id, is_verified, has_site, crm_enabled, created_at
        FROM sellers
        WHERE telegram_id = $1
        LIMIT 1
        """,
        telegram_id,
    )


async def get_seller_specialization_tags(seller_id: int) -> list[str]:
    rows = await fetch(
        """
        SELECT category AS tag FROM services WHERE seller_id = $1 AND category IS NOT NULL
        UNION
        SELECT title AS tag FROM services WHERE seller_id = $1 AND title IS NOT NULL
        UNION
        SELECT b.name AS tag
        FROM seller_cars sc
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.seller_id = $1
        UNION
        SELECT m.name AS tag
        FROM seller_cars sc
        JOIN models m ON m.id = sc.model_id
        WHERE sc.seller_id = $1
        """,
        seller_id,
    )
    return [row["tag"] for row in rows if row["tag"]]


async def list_matching_seller_leads(seller_id: int, *, limit: int = 10):
    normalized_limit = max(1, min(int(limit or 10), 25))
    return await fetch(
        """
        WITH seller_profile AS (
            SELECT id, city, is_verified, has_site, crm_enabled
            FROM sellers
            WHERE id = $1
            LIMIT 1
        ), seller_specs AS (
            SELECT LOWER(category) AS tag FROM services WHERE seller_id = $1 AND category IS NOT NULL
            UNION
            SELECT LOWER(title) AS tag FROM services WHERE seller_id = $1 AND title IS NOT NULL
            UNION
            SELECT LOWER(description) AS tag FROM services WHERE seller_id = $1 AND description IS NOT NULL
            UNION
            SELECT LOWER(b.name) AS tag
            FROM seller_cars sc
            JOIN models m ON m.id = sc.model_id
            JOIN brands b ON b.id = m.brand_id
            WHERE sc.seller_id = $1
            UNION
            SELECT LOWER(m.name) AS tag
            FROM seller_cars sc
            JOIN models m ON m.id = sc.model_id
            WHERE sc.seller_id = $1
            UNION
            SELECT LOWER(description) AS tag FROM seller_cars WHERE seller_id = $1 AND description IS NOT NULL
        )
        SELECT br.id, br.buyer_name, br.city, br.request_type, br.category,
               br.brand, br.model, br.vin, br.description, br.photos,
               br.urgency, br.marketplace_status, br.created_at,
               COALESCE(offer_counts.total_offers, 0) AS offers_count,
               route_event.id AS route_event_id,
               COALESCE(
                   NULLIF(route_event.payload->>'score', '')::int,
                   (
                       CASE WHEN sp.city IS NOT NULL AND br.city ILIKE sp.city THEN 40 ELSE 0 END +
                       CASE WHEN EXISTS (
                           SELECT 1 FROM seller_specs ss
                           WHERE ss.tag <> ''
                             AND (
                                  LOWER(COALESCE(br.category, '')) LIKE '%' || ss.tag || '%'
                               OR LOWER(COALESCE(br.request_type, '')) LIKE '%' || ss.tag || '%'
                               OR LOWER(COALESCE(br.brand, '')) LIKE '%' || ss.tag || '%'
                               OR LOWER(COALESCE(br.model, '')) LIKE '%' || ss.tag || '%'
                               OR LOWER(COALESCE(br.description, '')) LIKE '%' || ss.tag || '%'
                             )
                       ) THEN 35 ELSE 0 END +
                       CASE WHEN br.urgency = 'today' THEN 15 ELSE 0 END +
                       CASE WHEN sp.is_verified THEN 5 ELSE 0 END +
                       CASE WHEN sp.has_site OR sp.crm_enabled THEN 5 ELSE 0 END
                   )
               ) AS match_score,
               route_event.payload->'reasons' AS match_reasons
        FROM buyer_requests br
        CROSS JOIN seller_profile sp
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS total_offers
            FROM buyer_request_offers bro
            WHERE bro.request_id = br.id
        ) offer_counts ON TRUE
        LEFT JOIN LATERAL (
            SELECT id, payload, status
            FROM marketplace_notification_events mne
            WHERE mne.event_type = 'buyer_request_created'
              AND mne.request_id = br.id
              AND mne.seller_id = $1
            ORDER BY mne.created_at DESC, mne.id DESC
            LIMIT 1
        ) route_event ON TRUE
        WHERE br.entity_type = 'marketplace_request'
          AND br.marketplace_status IN ('pending', 'active', 'matched')
          AND NOT EXISTS (
              SELECT 1 FROM buyer_request_offers bro
              WHERE bro.request_id = br.id AND bro.seller_id = $1
          )
          AND NOT EXISTS (
              SELECT 1 FROM seller_lead_actions sla
              WHERE sla.request_id = br.id AND sla.seller_id = $1 AND sla.action IN ('skipped', 'declined')
          )
          AND (
              route_event.id IS NOT NULL
              OR sp.city IS NULL
              OR br.city ILIKE sp.city
              OR EXISTS (
                  SELECT 1 FROM seller_specs ss
                  WHERE ss.tag <> ''
                    AND (
                         LOWER(COALESCE(br.category, '')) LIKE '%' || ss.tag || '%'
                      OR LOWER(COALESCE(br.request_type, '')) LIKE '%' || ss.tag || '%'
                      OR LOWER(COALESCE(br.brand, '')) LIKE '%' || ss.tag || '%'
                      OR LOWER(COALESCE(br.model, '')) LIKE '%' || ss.tag || '%'
                      OR LOWER(COALESCE(br.description, '')) LIKE '%' || ss.tag || '%'
                    )
              )
          )
        ORDER BY route_event.id IS NOT NULL DESC, match_score DESC, br.created_at DESC, br.id DESC
        LIMIT $2
        """,
        seller_id,
        normalized_limit,
    )

async def get_matching_seller_lead(seller_id: int, request_id: int):
    row = await fetchrow(
        """
        WITH seller_profile AS (
            SELECT id, city, is_verified, has_site, crm_enabled
            FROM sellers
            WHERE id = $1
            LIMIT 1
        ), seller_specs AS (
            SELECT LOWER(category) AS tag FROM services WHERE seller_id = $1 AND category IS NOT NULL
            UNION
            SELECT LOWER(title) AS tag FROM services WHERE seller_id = $1 AND title IS NOT NULL
            UNION
            SELECT LOWER(description) AS tag FROM services WHERE seller_id = $1 AND description IS NOT NULL
            UNION
            SELECT LOWER(b.name) AS tag
            FROM seller_cars sc
            JOIN models m ON m.id = sc.model_id
            JOIN brands b ON b.id = m.brand_id
            WHERE sc.seller_id = $1
            UNION
            SELECT LOWER(m.name) AS tag
            FROM seller_cars sc
            JOIN models m ON m.id = sc.model_id
            WHERE sc.seller_id = $1
            UNION
            SELECT LOWER(description) AS tag FROM seller_cars WHERE seller_id = $1 AND description IS NOT NULL
        )
        SELECT br.id, br.buyer_name, br.city, br.request_type, br.category,
               br.brand, br.model, br.vin, br.description, br.photos,
               br.urgency, br.marketplace_status, br.created_at,
               COALESCE(offer_counts.total_offers, 0) AS offers_count,
               route_event.id AS route_event_id,
               COALESCE(
                   NULLIF(route_event.payload->>'score', '')::int,
                   (
                       CASE WHEN sp.city IS NOT NULL AND br.city ILIKE sp.city THEN 40 ELSE 0 END +
                       CASE WHEN EXISTS (
                           SELECT 1 FROM seller_specs ss
                           WHERE ss.tag <> ''
                             AND (
                                  LOWER(COALESCE(br.category, '')) LIKE '%' || ss.tag || '%'
                               OR LOWER(COALESCE(br.request_type, '')) LIKE '%' || ss.tag || '%'
                               OR LOWER(COALESCE(br.brand, '')) LIKE '%' || ss.tag || '%'
                               OR LOWER(COALESCE(br.model, '')) LIKE '%' || ss.tag || '%'
                               OR LOWER(COALESCE(br.description, '')) LIKE '%' || ss.tag || '%'
                             )
                       ) THEN 35 ELSE 0 END +
                       CASE WHEN br.urgency = 'today' THEN 15 ELSE 0 END +
                       CASE WHEN sp.is_verified THEN 5 ELSE 0 END +
                       CASE WHEN sp.has_site OR sp.crm_enabled THEN 5 ELSE 0 END
                   )
               ) AS match_score,
               route_event.payload->'reasons' AS match_reasons
        FROM buyer_requests br
        CROSS JOIN seller_profile sp
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS total_offers
            FROM buyer_request_offers bro
            WHERE bro.request_id = br.id
        ) offer_counts ON TRUE
        LEFT JOIN LATERAL (
            SELECT id, payload, status
            FROM marketplace_notification_events mne
            WHERE mne.event_type = 'buyer_request_created'
              AND mne.request_id = br.id
              AND mne.seller_id = $1
            ORDER BY mne.created_at DESC, mne.id DESC
            LIMIT 1
        ) route_event ON TRUE
        WHERE br.id = $2
          AND br.entity_type = 'marketplace_request'
          AND br.marketplace_status IN ('pending', 'active', 'matched')
          AND NOT EXISTS (
              SELECT 1 FROM seller_lead_actions sla
              WHERE sla.request_id = br.id AND sla.seller_id = $1 AND sla.action IN ('skipped', 'declined')
          )
          AND (
              route_event.id IS NOT NULL
              OR sp.city IS NULL
              OR br.city ILIKE sp.city
              OR EXISTS (
                  SELECT 1 FROM seller_specs ss
                  WHERE ss.tag <> ''
                    AND (
                         LOWER(COALESCE(br.category, '')) LIKE '%' || ss.tag || '%'
                      OR LOWER(COALESCE(br.request_type, '')) LIKE '%' || ss.tag || '%'
                      OR LOWER(COALESCE(br.brand, '')) LIKE '%' || ss.tag || '%'
                      OR LOWER(COALESCE(br.model, '')) LIKE '%' || ss.tag || '%'
                      OR LOWER(COALESCE(br.description, '')) LIKE '%' || ss.tag || '%'
                    )
              )
          )
        LIMIT 1
        """,
        seller_id,
        request_id,
    )
    return row

async def mark_seller_lead_action(
    *,
    seller_id: int,
    request_id: int,
    action: str,
    metadata: dict | None = None,
):
    _validate(action, SELLER_LEAD_ACTIONS, "Invalid seller lead action")
    return await fetchrow(
        """
        INSERT INTO seller_lead_actions (seller_id, request_id, action, metadata, updated_at)
        VALUES ($1, $2, $3, COALESCE($4::jsonb, '{}'::jsonb), NOW())
        ON CONFLICT (seller_id, request_id, action)
        DO UPDATE SET metadata = EXCLUDED.metadata, updated_at = NOW()
        RETURNING id, seller_id, request_id, action, metadata, created_at, updated_at
        """,
        seller_id,
        request_id,
        action,
        json.dumps(metadata or {}, ensure_ascii=False),
    )


async def cancel_seller_lead_notifications(*, seller_id: int, request_id: int) -> None:
    await execute(
        """
        UPDATE marketplace_notification_events
        SET status = 'cancelled', updated_at = NOW()
        WHERE event_type = 'buyer_request_created'
          AND request_id = $1
          AND seller_id = $2
          AND status = 'pending'
        """,
        request_id,
        seller_id,
    )


async def create_seller_offer(
    *,
    request_id: int,
    seller_id: int,
    message: str,
    price_offer: Decimal | None,
    availability_note: str | None,
    status: str = "pending",
):
    _validate(status, BUYER_REQUEST_OFFER_STATUSES, "Invalid buyer request offer status")
    return await fetchrow(
        """
        WITH existing AS (
            UPDATE buyer_request_offers
            SET message = $3,
                price_offer = $4,
                availability_note = $5,
                status = $6,
                updated_at = NOW()
            WHERE request_id = $1 AND seller_id = $2
            RETURNING id, request_id, seller_id, message, price_offer,
                      availability_note, status, created_at, updated_at
        ), inserted AS (
            INSERT INTO buyer_request_offers (
                request_id, seller_id, message, price_offer, availability_note, status
            )
            SELECT $1, $2, $3, $4, $5, $6
            WHERE NOT EXISTS (SELECT 1 FROM existing)
            RETURNING id, request_id, seller_id, message, price_offer,
                      availability_note, status, created_at, updated_at
        )
        SELECT * FROM existing
        UNION ALL
        SELECT * FROM inserted
        LIMIT 1
        """,
        request_id,
        seller_id,
        message,
        price_offer,
        availability_note,
        status,
    )


async def list_offer_delivery_payloads(request_id: int):
    return await fetch(
        """
        SELECT bro.id, bro.request_id, bro.seller_id, bro.message, bro.price_offer,
               bro.availability_note, bro.status, bro.created_at,
               s.shop_name, s.name AS seller_name, s.username AS seller_username,
               s.phone AS seller_phone, s.website AS seller_website,
               s.city AS seller_city, s.is_verified, s.has_site, s.crm_enabled,
               COALESCE(successful.successful_offers, 0) AS successful_offers,
               COALESCE(activity.total_offers, 0) AS marketplace_activity
        FROM buyer_request_offers bro
        JOIN sellers s ON s.id = bro.seller_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS successful_offers
            FROM buyer_request_offers accepted
            WHERE accepted.seller_id = s.id AND accepted.status = 'accepted'
        ) successful ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS total_offers
            FROM buyer_request_offers seller_offers
            WHERE seller_offers.seller_id = s.id
        ) activity ON TRUE
        WHERE bro.request_id = $1
        ORDER BY bro.created_at DESC, bro.id DESC
        """,
        request_id,
    )


async def touch_request_matched(request_id: int):
    await execute(
        """
        UPDATE buyer_requests
        SET marketplace_status = CASE
                WHEN marketplace_status = 'pending' THEN 'matched'
                ELSE marketplace_status
            END,
            updated_at = NOW()
        WHERE id = $1
        """,
        request_id,
    )


async def get_buyer_offer_notification_context(*, request_id: int, seller_id: int, offer_id: int):
    return await fetchrow(
        """
        SELECT br.id AS request_id, br.telegram_id AS buyer_telegram_id,
               br.brand, br.model, br.category, br.request_type, br.description,
               s.shop_name, s.name AS seller_name, s.city AS seller_city,
               bro.id AS offer_id, bro.message, bro.price_offer
        FROM buyer_request_offers bro
        JOIN buyer_requests br ON br.id = bro.request_id
        JOIN sellers s ON s.id = bro.seller_id
        WHERE bro.id = $1
          AND bro.request_id = $2
          AND bro.seller_id = $3
          AND br.entity_type = 'marketplace_request'
        LIMIT 1
        """,
        offer_id,
        request_id,
        seller_id,
    )


async def ensure_buyer_offer_created_event(*, request_id: int, seller_id: int, offer_id: int):
    existing = await fetchrow(
        """
        SELECT id, event_type, request_id, offer_id, seller_id, payload, status, created_at
        FROM marketplace_notification_events
        WHERE event_type = 'buyer_offer_created'
          AND offer_id = $1
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        offer_id,
    )
    if existing:
        event = dict(existing)
        event["already_exists"] = True
        return event

    inserted = await fetchrow(
        """
        INSERT INTO marketplace_notification_events (
            event_type, request_id, offer_id, seller_id, payload, status, created_at, updated_at
        )
        VALUES (
            'buyer_offer_created',
            $1::int,
            $2::int,
            $3::int,
            jsonb_build_object(
                'request_id', $1::int,
                'offer_id', $2::int,
                'seller_id', $3::int
            ),
            'pending',
            NOW(),
            NOW()
        )
        RETURNING id, event_type, request_id, offer_id, seller_id, payload, status, created_at
        """,
        request_id,
        offer_id,
        seller_id,
    )
    event = dict(inserted) if inserted else {}
    event["already_exists"] = False
    return event


async def mark_marketplace_notification_event(event_id: int | None, *, status: str) -> None:
    if not event_id:
        return
    await execute(
        """
        UPDATE marketplace_notification_events
        SET status = $2, updated_at = NOW()
        WHERE id = $1
        """,
        event_id,
        status,
    )
