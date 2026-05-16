import logging

from bot.database.base import fetch, fetchrow, transaction


BUYER_REQUEST_STATUSES = {"pending", "active", "matched", "closed"}
BUYER_REQUEST_OFFER_STATUSES = {"pending", "accepted", "rejected"}
MATCH_STATUSES = {"matched", "contacted", "closed", "cancelled"}
logger = logging.getLogger(__name__)


def _validate(value: str, allowed: set[str], message: str) -> None:
    if value not in allowed:
        raise ValueError(message)


async def get_buyer_request_for_offer_view(request_id: int):
    return await fetchrow(
        """
        SELECT br.id, br.buyer_name, br.city, br.request_type, br.category,
               br.brand, br.model, br.vin, br.description, br.urgency,
               br.marketplace_status, br.created_at, br.updated_at,
               accepted.offer_id AS accepted_offer_id,
               COALESCE(offer_counts.total_offers, 0)::int AS offers_count,
               COALESCE(offer_counts.new_offers, 0)::int AS new_offers_count
        FROM buyer_requests br
        LEFT JOIN marketplace_matches accepted
               ON accepted.request_id = br.id
              AND accepted.status IN ('matched', 'contacted', 'closed')
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS total_offers,
                   COUNT(*) FILTER (WHERE bro.status = 'pending')::int AS new_offers
            FROM buyer_request_offers bro
            WHERE bro.request_id = br.id
        ) offer_counts ON TRUE
        WHERE br.id = $1
          AND br.entity_type = 'marketplace_request'
        LIMIT 1
        """,
        request_id,
    )


async def list_buyer_offer_cards(request_id: int):
    return await fetch(
        """
        SELECT bro.id, bro.request_id, bro.seller_id, bro.message, bro.price_offer,
               bro.availability_note, bro.status, bro.created_at, bro.updated_at,
               s.shop_name, s.name AS seller_name, s.username AS seller_username,
               s.phone AS seller_phone, s.website AS seller_website,
               s.city AS seller_city, s.is_verified, s.has_site, s.crm_enabled,
               s.description AS seller_description,
               COALESCE(successful.successful_offers, 0)::int AS successful_offers,
               COALESCE(activity.total_offers, 0)::int AS marketplace_activity,
               response.avg_response_seconds,
               response.last_response_seconds,
               CASE WHEN match.offer_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_selected_match
        FROM buyer_request_offers bro
        JOIN sellers s ON s.id = bro.seller_id
        LEFT JOIN marketplace_matches match
               ON match.offer_id = bro.id
              AND match.status IN ('matched', 'contacted', 'closed')
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
        LEFT JOIN LATERAL (
            SELECT AVG(EXTRACT(EPOCH FROM (offered.updated_at - viewed.updated_at)))::int AS avg_response_seconds,
                   MAX(EXTRACT(EPOCH FROM (offered.updated_at - viewed.updated_at)))::int AS last_response_seconds
            FROM seller_lead_actions offered
            JOIN seller_lead_actions viewed
              ON viewed.seller_id = offered.seller_id
             AND viewed.request_id = offered.request_id
             AND viewed.action = 'viewed'
            WHERE offered.seller_id = s.id
              AND offered.action = 'offered'
              AND offered.updated_at >= viewed.updated_at
        ) response ON TRUE
        WHERE bro.request_id = $1
        ORDER BY
            CASE bro.status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
            s.is_verified DESC,
            bro.created_at DESC,
            bro.id DESC
        """,
        request_id,
    )


async def get_buyer_offer_detail(request_id: int, offer_id: int):
    return await fetchrow(
        """
        SELECT bro.id, bro.request_id, bro.seller_id, bro.message, bro.price_offer,
               bro.availability_note, bro.status, bro.created_at, bro.updated_at,
               s.shop_name, s.name AS seller_name, s.username AS seller_username,
               s.phone AS seller_phone, s.website AS seller_website,
               s.city AS seller_city, s.is_verified, s.has_site, s.crm_enabled,
               s.description AS seller_description
        FROM buyer_request_offers bro
        JOIN sellers s ON s.id = bro.seller_id
        WHERE bro.request_id = $1 AND bro.id = $2
        LIMIT 1
        """,
        request_id,
        offer_id,
    )


async def accept_buyer_offer(request_id: int, offer_id: int, *, reject_other_offers: bool = True):
    async with transaction() as conn:
        selected = await conn.fetchrow(
            """
            SELECT bro.id, bro.request_id, bro.seller_id, bro.status,
                   br.marketplace_status
            FROM buyer_request_offers bro
            JOIN buyer_requests br ON br.id = bro.request_id
            WHERE bro.request_id = $1
              AND bro.id = $2
              AND br.entity_type = 'marketplace_request'
              AND br.marketplace_status IN ('pending', 'active', 'matched')
              AND NOT EXISTS (
                  SELECT 1 FROM marketplace_matches existing_match
                  WHERE existing_match.request_id = br.id
                    AND existing_match.status IN ('matched', 'contacted', 'closed')
                    AND existing_match.offer_id <> $2
              )
            FOR UPDATE OF bro, br
            """,
            request_id,
            offer_id,
        )
        if not selected:
            return None

        await conn.execute(
            """
            UPDATE buyer_request_offers
            SET status = 'accepted', updated_at = NOW()
            WHERE request_id = $1 AND id = $2
            """,
            request_id,
            offer_id,
        )

        if reject_other_offers:
            await conn.execute(
                """
                UPDATE buyer_request_offers
                SET status = 'rejected', updated_at = NOW()
                WHERE request_id = $1 AND id <> $2 AND status = 'pending'
                """,
                request_id,
                offer_id,
            )

        await conn.execute(
            """
            UPDATE buyer_requests
            SET marketplace_status = 'matched', updated_at = NOW()
            WHERE id = $1
            """,
            request_id,
        )

        match = await conn.fetchrow(
            """
            INSERT INTO marketplace_matches (request_id, offer_id, seller_id, status, matched_at, updated_at)
            VALUES ($1, $2, $3, 'matched', NOW(), NOW())
            ON CONFLICT (request_id)
            DO UPDATE SET offer_id = EXCLUDED.offer_id,
                          seller_id = EXCLUDED.seller_id,
                          status = 'matched',
                          matched_at = NOW(),
                          updated_at = NOW()
            RETURNING id, request_id, offer_id, seller_id, status, matched_at, updated_at
            """,
            request_id,
            offer_id,
            selected["seller_id"],
        )

        notification = await conn.fetchrow(
            """
            INSERT INTO marketplace_notification_events (
                event_type, request_id, offer_id, seller_id, payload, status, created_at, updated_at
            )
            VALUES (
                'seller_offer_accepted', $1, $2, $3,
                jsonb_build_object(
                    'request_id', $1::bigint,
                    'offer_id', $2::bigint,
                    'seller_id', $3::bigint
                ),
                'pending', NOW(), NOW()
            )
            RETURNING id, event_type, request_id, offer_id, seller_id, payload, status, created_at
            """,
            request_id,
            offer_id,
            selected["seller_id"],
        )

        logger.info(
            "Buyer accepted seller offer request_id=%s offer_id=%s seller_id=%s match_id=%s notification_event_id=%s",
            request_id,
            offer_id,
            selected["seller_id"],
            match["id"] if match else None,
            notification["id"] if notification else None,
        )
        return {"match": dict(match) if match else None, "notification_event": dict(notification) if notification else None}


async def get_marketplace_match_for_request(request_id: int):
    return await fetchrow(
        """
        SELECT mm.id, mm.request_id, mm.offer_id, mm.seller_id, mm.status,
               mm.matched_at, mm.updated_at
        FROM marketplace_matches mm
        WHERE mm.request_id = $1
        LIMIT 1
        """,
        request_id,
    )
