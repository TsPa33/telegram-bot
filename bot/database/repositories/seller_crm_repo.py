from datetime import datetime
import json
import logging

from bot.database.base import execute, fetch, fetchrow

logger = logging.getLogger(__name__)


async def create_crm_subscription(
    seller_id: int,
    payment_id: int,
    days: int = 30,
    status: str = "active",
):
    logger.info(
        "CRM_SUBSCRIPTION_CREATE_REQUEST seller_id=%s payment_id=%s days=%s",
        seller_id,
        payment_id,
        days,
    )

    existing = await fetchrow(
        """
        SELECT *
        FROM seller_crm_subscriptions
        WHERE payment_id = $1
        LIMIT 1
        """,
        payment_id,
    )
    if existing:
        await execute("UPDATE sellers SET crm_enabled = TRUE WHERE id = $1", seller_id)
        logger.info("CRM_SUBSCRIPTION_ALREADY_EXISTS payment_id=%s", payment_id)
        return existing

    await execute("UPDATE sellers SET crm_enabled = TRUE WHERE id = $1", seller_id)

    subscription = await fetchrow(
        """
        INSERT INTO seller_crm_subscriptions (
            seller_id,
            payment_id,
            status,
            started_at,
            expires_at
        )
        VALUES (
            $1,
            $2,
            $3,
            NOW(),
            NOW() + ($4::int * INTERVAL '1 day')
        )
        ON CONFLICT (payment_id) DO NOTHING
        RETURNING *
        """,
        seller_id,
        payment_id,
        status,
        days,
    )

    if subscription:
        logger.info(
            "CRM_SUBSCRIPTION_ACTIVATED seller_id=%s payment_id=%s",
            seller_id,
            payment_id,
        )
        return subscription

    existing = await fetchrow(
        """
        SELECT *
        FROM seller_crm_subscriptions
        WHERE payment_id = $1
        LIMIT 1
        """,
        payment_id,
    )
    if existing:
        await execute("UPDATE sellers SET crm_enabled = TRUE WHERE id = $1", seller_id)
        logger.info("CRM_SUBSCRIPTION_ALREADY_EXISTS payment_id=%s", payment_id)
        return existing

    raise RuntimeError(f"CRM subscription was not created for payment_id={payment_id}")


async def get_successful_crm_payment_without_subscription(seller_id: int, product_type: str):
    return await fetchrow(
        """
        SELECT p.*
        FROM payments p
        LEFT JOIN seller_crm_subscriptions scs ON scs.payment_id = p.id
        WHERE p.seller_id = $1
          AND p.status = 'success'
          AND COALESCE(p.product_type, p.product) = $2
          AND scs.id IS NULL
        ORDER BY p.created_at DESC, p.id DESC
        LIMIT 1
        """,
        seller_id,
        product_type,
    )


async def get_active_crm_subscription(seller_id: int):
    return await fetchrow(
        """
        SELECT *
        FROM seller_crm_subscriptions
        WHERE seller_id = $1
          AND status = 'active'
          AND expires_at > NOW()
        ORDER BY expires_at DESC, id DESC
        LIMIT 1
        """,
        seller_id,
    )


async def get_latest_crm_subscription(seller_id: int):
    return await fetchrow(
        """
        SELECT *
        FROM seller_crm_subscriptions
        WHERE seller_id = $1
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        seller_id,
    )


async def seller_has_active_crm(seller_id: int) -> bool:
    row = await fetchrow(
        """
        SELECT 1
        FROM sellers s
        JOIN seller_crm_subscriptions scs ON scs.seller_id = s.id
        WHERE s.id = $1
          AND COALESCE(s.crm_enabled, FALSE) = TRUE
          AND scs.status = 'active'
          AND scs.expires_at > NOW()
        LIMIT 1
        """,
        seller_id,
    )
    return row is not None


async def get_crm_account_by_seller(seller_id: int):
    return await fetchrow(
        """
        SELECT *
        FROM seller_crm_accounts
        WHERE seller_id = $1
        LIMIT 1
        """,
        seller_id,
    )


async def enable_seller_crm(seller_id: int) -> None:
    await execute("UPDATE sellers SET crm_enabled = TRUE WHERE id = $1", seller_id)


def _slug_candidates(base_slug: str, seller_id: int) -> list[str]:
    base_slug = (base_slug or "").strip("-")[:40]
    if len(base_slug) < 3:
        base_slug = f"seller-{seller_id}"

    candidates = [base_slug]
    suffixes = [str(seller_id), *[str(index) for index in range(2, 21)]]
    for suffix in suffixes:
        prefix = base_slug[: max(1, 39 - len(suffix))].strip("-")
        candidates.append(f"{prefix}-{suffix}" if prefix else f"seller-{seller_id}")

    fallback = f"seller-{seller_id}"
    if fallback not in candidates:
        candidates.append(fallback)

    seen = set()
    unique = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


async def ensure_free_crm_account(
    *,
    seller_id: int,
    base_slug: str,
    password_hash: str,
):
    await enable_seller_crm(seller_id)

    existing = await get_crm_account_by_seller(seller_id)
    if existing:
        logger.info(
            "CRM_FREE_ACCESS_EXISTING seller_id=%s slug=%s",
            seller_id,
            existing["crm_slug"],
        )
        return existing, False

    for slug in _slug_candidates(base_slug, seller_id):
        account = await fetchrow(
            """
            INSERT INTO seller_crm_accounts (seller_id, crm_slug, password_hash, is_active)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT DO NOTHING
            RETURNING *
            """,
            seller_id,
            slug,
            password_hash,
        )
        if account:
            logger.info("CRM_AUTO_PROVISIONED seller_id=%s slug=%s", seller_id, slug)
            return account, True

        existing = await get_crm_account_by_seller(seller_id)
        if existing:
            logger.info(
                "CRM_FREE_ACCESS_RACE_RESOLVED seller_id=%s slug=%s",
                seller_id,
                existing["crm_slug"],
            )
            return existing, False

    raise RuntimeError(f"Unable to provision seller CRM account for seller_id={seller_id}")


async def get_crm_account_by_slug(crm_slug: str):
    return await fetchrow(
        """
        SELECT sca.*, s.telegram_id, s.username, s.shop_name, s.name, s.crm_enabled, s.has_site, s.website, s.city
        FROM seller_crm_accounts sca
        JOIN sellers s ON s.id = sca.seller_id
        WHERE lower(sca.crm_slug) = lower($1)
        LIMIT 1
        """,
        crm_slug,
    )


async def get_crm_account_for_login(identifier: str, crm_slug: str | None = None):
    identifier = (identifier or "").strip()
    if crm_slug:
        return await fetchrow(
            """
            SELECT sca.*, s.telegram_id, s.username, s.shop_name, s.name, s.crm_enabled
            FROM seller_crm_accounts sca
            JOIN sellers s ON s.id = sca.seller_id
            WHERE lower(sca.crm_slug) = lower($1)
              AND ($2 = s.telegram_id::text OR lower($2) = lower(COALESCE(s.username, '')))
            LIMIT 1
            """,
            crm_slug,
            identifier,
        )

    return await fetchrow(
        """
        SELECT sca.*, s.telegram_id, s.username, s.shop_name, s.name, s.crm_enabled
        FROM seller_crm_accounts sca
        JOIN sellers s ON s.id = sca.seller_id
        WHERE $1 = s.telegram_id::text
           OR lower(sca.crm_slug) = lower($1)
           OR lower($1) = lower(COALESCE(s.username, ''))
        ORDER BY sca.id DESC
        LIMIT 1
        """,
        identifier,
    )


async def upsert_crm_account(seller_id: int, crm_slug: str, password_hash: str):
    return await fetchrow(
        """
        INSERT INTO seller_crm_accounts (seller_id, crm_slug, password_hash, is_active)
        VALUES ($1, $2, $3, TRUE)
        ON CONFLICT (seller_id)
        DO UPDATE SET
            crm_slug = EXCLUDED.crm_slug,
            password_hash = EXCLUDED.password_hash,
            is_active = TRUE
        RETURNING *
        """,
        seller_id,
        crm_slug,
        password_hash,
    )


async def create_crm_session(account_id: int, token: str, expires_at: datetime):
    return await fetchrow(
        """
        INSERT INTO seller_crm_sessions (account_id, token, expires_at)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        account_id,
        token,
        expires_at,
    )


async def get_crm_session(token: str):
    return await fetchrow(
        """
        SELECT scs.*, sca.seller_id, sca.crm_slug, sca.is_active, s.crm_enabled,
               s.telegram_id, s.username, s.shop_name, s.name
        FROM seller_crm_sessions scs
        JOIN seller_crm_accounts sca ON sca.id = scs.account_id
        JOIN sellers s ON s.id = sca.seller_id
        WHERE scs.token = $1
        LIMIT 1
        """,
        token,
    )


async def delete_crm_session(token: str):
    await execute("DELETE FROM seller_crm_sessions WHERE token = $1", token)


async def get_seller_crm_dashboard(seller_id: int):
    return await fetchrow(
        """
        WITH seller_site AS (
            SELECT id, subdomain FROM seller_sites WHERE seller_id = $1 LIMIT 1
        ), lead_counts AS (
            SELECT
                COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE)::int AS leads_today,
                COUNT(*) FILTER (WHERE status = 'new')::int AS new_leads,
                COUNT(*) FILTER (WHERE status = 'in_progress')::int AS in_progress_leads,
                COUNT(*) FILTER (WHERE status IN ('done', 'rejected'))::int AS closed_leads
            FROM site_leads WHERE seller_id = $1
        ), session_counts AS (
            SELECT
                COUNT(*) FILTER (WHERE started_at >= CURRENT_DATE)::int AS visits_today,
                COALESCE(SUM(pages_viewed) FILTER (WHERE started_at >= CURRENT_DATE), 0)::int AS page_views_today
            FROM analytics_sessions a
            JOIN seller_site ss ON ss.id = a.seller_site_id OR lower(ss.subdomain) = lower(a.subdomain)
        ), event_counts AS (
            SELECT
                COUNT(*) FILTER (WHERE event_type = 'telegram_click' AND created_at >= CURRENT_DATE)::int AS telegram_clicks_today,
                COUNT(*) FILTER (WHERE event_type IN ('cta_click', 'phone_click', 'site_click') AND created_at >= CURRENT_DATE)::int AS cta_clicks_today
            FROM analytics_events e
            JOIN seller_site ss ON ss.id = e.seller_site_id OR lower(ss.subdomain) = lower(e.subdomain)
        ), car_counts AS (
            SELECT COUNT(*)::int AS active_listings, COALESCE(SUM(views), 0)::int AS listing_views,
                   COALESCE(SUM(phone_clicks + site_clicks), 0)::int AS listing_clicks
            FROM seller_cars WHERE seller_id = $1
        ), service_counts AS (
            SELECT COUNT(*)::int AS services_count, COALESCE(SUM(st.views), 0)::int AS service_views,
                   COALESCE(SUM(st.calls + st.clicks), 0)::int AS service_requests
            FROM services sv LEFT JOIN service_stats st ON st.service_id = sv.id
            WHERE sv.seller_id = $1
        )
        SELECT
            COALESCE(sc.visits_today, 0)::int AS visits_today,
            COALESCE(lc.leads_today, 0)::int AS leads_today,
            COALESCE(ec.telegram_clicks_today, 0)::int AS telegram_clicks_today,
            COALESCE(cc.active_listings, 0)::int AS active_listings,
            CASE WHEN COALESCE(sc.visits_today, 0) = 0 THEN 0
                 ELSE ROUND((COALESCE(lc.leads_today, 0)::numeric / sc.visits_today::numeric) * 100, 1)
            END AS conversion,
            COALESCE(lc.new_leads, 0)::int AS new_leads,
            COALESCE(lc.in_progress_leads, 0)::int AS in_progress_leads,
            COALESCE(lc.closed_leads, 0)::int AS closed_leads,
            COALESCE(sc.page_views_today, 0)::int AS page_views_today,
            COALESCE(ec.cta_clicks_today, 0)::int AS cta_clicks_today,
            COALESCE(cc.listing_views, 0)::int AS listing_views,
            COALESCE(cc.listing_clicks, 0)::int AS listing_clicks,
            COALESCE(src.services_count, 0)::int AS services_count,
            COALESCE(src.service_views, 0)::int AS service_views,
            COALESCE(src.service_requests, 0)::int AS service_requests
        FROM lead_counts lc
        CROSS JOIN session_counts sc
        CROSS JOIN event_counts ec
        CROSS JOIN car_counts cc
        CROSS JOIN service_counts src
        """,
        seller_id,
    )


async def get_seller_crm_marketplace_summary(seller_id: int):
    return await fetchrow(
        """
        WITH relevant_requests AS (
            SELECT DISTINCT br.id, br.created_at
            FROM buyer_requests br
            LEFT JOIN marketplace_notification_events mne
              ON mne.request_id = br.id
             AND mne.seller_id = $1
             AND mne.event_type = 'buyer_request_created'
            LEFT JOIN buyer_request_offers bro
              ON bro.request_id = br.id
             AND bro.seller_id = $1
            WHERE br.entity_type = 'marketplace_request'
              AND (mne.id IS NOT NULL OR bro.id IS NOT NULL OR br.seller_id = $1)
        ), pending_requests AS (
            SELECT rr.id
            FROM relevant_requests rr
            WHERE NOT EXISTS (
                SELECT 1 FROM buyer_request_offers bro
                WHERE bro.request_id = rr.id AND bro.seller_id = $1
            )
              AND NOT EXISTS (
                SELECT 1 FROM seller_lead_actions sla
                WHERE sla.request_id = rr.id
                  AND sla.seller_id = $1
                  AND sla.action IN ('skipped', 'declined', 'offered')
            )
        ), response_pairs AS (
            SELECT EXTRACT(EPOCH FROM (bro.created_at - COALESCE(mne.created_at, br.created_at)))::int AS response_seconds
            FROM buyer_request_offers bro
            JOIN buyer_requests br ON br.id = bro.request_id
            LEFT JOIN LATERAL (
                SELECT created_at
                FROM marketplace_notification_events route_event
                WHERE route_event.request_id = bro.request_id
                  AND route_event.seller_id = bro.seller_id
                  AND route_event.event_type = 'buyer_request_created'
                ORDER BY route_event.created_at ASC, route_event.id ASC
                LIMIT 1
            ) mne ON TRUE
            WHERE bro.seller_id = $1
              AND bro.created_at >= COALESCE(mne.created_at, br.created_at)
        )
        SELECT
            (SELECT COUNT(*)::int FROM relevant_requests WHERE created_at >= NOW() - INTERVAL '24 hours') AS new_requests,
            (SELECT COUNT(*)::int FROM pending_requests) AS waiting_response,
            (SELECT COUNT(*)::int FROM buyer_request_offers WHERE seller_id = $1 AND status = 'accepted') AS accepted_offers,
            (SELECT AVG(response_seconds)::int FROM response_pairs) AS avg_response_seconds,
            (SELECT COUNT(*)::int FROM buyer_request_offers WHERE seller_id = $1) AS total_offers
        """,
        seller_id,
    )


async def list_seller_crm_marketplace_requests(seller_id: int, limit: int = 8):
    normalized_limit = max(1, min(int(limit or 8), 20))
    return await fetch(
        """
        SELECT br.id, br.city, br.request_type, br.category, br.brand, br.model,
               br.description, br.message, br.marketplace_status, br.created_at,
               route_event.status AS notification_status,
               bro.id AS offer_id, bro.status AS offer_status, bro.created_at AS offer_created_at,
               sla.action AS seller_action,
               COALESCE(offer_counts.total_offers, 0)::int AS offers_count
        FROM buyer_requests br
        LEFT JOIN LATERAL (
            SELECT id, status, created_at
            FROM marketplace_notification_events mne
            WHERE mne.request_id = br.id
              AND mne.seller_id = $1
              AND mne.event_type = 'buyer_request_created'
            ORDER BY mne.created_at DESC, mne.id DESC
            LIMIT 1
        ) route_event ON TRUE
        LEFT JOIN LATERAL (
            SELECT id, status, created_at
            FROM buyer_request_offers seller_offer
            WHERE seller_offer.request_id = br.id
              AND seller_offer.seller_id = $1
            ORDER BY seller_offer.created_at DESC, seller_offer.id DESC
            LIMIT 1
        ) bro ON TRUE
        LEFT JOIN LATERAL (
            SELECT action, updated_at
            FROM seller_lead_actions action_row
            WHERE action_row.request_id = br.id
              AND action_row.seller_id = $1
            ORDER BY action_row.updated_at DESC, action_row.id DESC
            LIMIT 1
        ) sla ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS total_offers
            FROM buyer_request_offers request_offer
            WHERE request_offer.request_id = br.id
        ) offer_counts ON TRUE
        WHERE br.entity_type = 'marketplace_request'
          AND (route_event.id IS NOT NULL OR bro.id IS NOT NULL OR br.seller_id = $1)
        ORDER BY GREATEST(
            br.created_at,
            COALESCE(route_event.created_at, br.created_at),
            COALESCE(bro.created_at, br.created_at)
        ) DESC, br.id DESC
        LIMIT $2
        """,
        seller_id,
        normalized_limit,
    )


async def list_seller_crm_marketplace_leads(
    seller_id: int,
    status: str = "new",
    limit: int = 30,
    offset: int = 0,
):
    allowed_statuses = {"new", "in_work", "replied", "selected", "declined", "skipped"}
    normalized_status = status if status in allowed_statuses else "new"
    normalized_limit = max(1, min(int(limit or 30), 50))
    normalized_offset = max(0, int(offset or 0))

    return await fetch(
        """
        WITH relevant_leads AS (
            SELECT br.id AS request_id,
                   NULLIF(CONCAT_WS(' ', br.brand, br.model), '') AS vehicle_title,
                   br.city, br.request_type, br.category, br.brand, br.model,
                   br.description, br.urgency, br.marketplace_status, br.created_at,
                   route_event.id AS route_event_id,
                   NULLIF(route_event.payload->>'score', '')::int AS routed_match_score,
                   route_event.payload->'reasons' AS routed_match_reasons,
                   seller_offer.id AS offer_id,
                   seller_offer.status AS offer_status,
                   seller_offer.price_offer,
                   seller_offer.message AS offer_message,
                   seller_offer.created_at AS offer_created_at,
                   selected_match.id AS selected_match_id,
                   selected_match.status AS selected_match_status,
                   selected_match.matched_at AS selected_matched_at,
                   actions.latest_action,
                   actions.latest_action_at,
                   COALESCE(actions.has_viewed, FALSE) AS has_viewed,
                   COALESCE(actions.has_offered, FALSE) AS has_offered,
                   COALESCE(actions.has_declined, FALSE) AS has_declined,
                   COALESCE(actions.has_skipped, FALSE) AS has_skipped,
                   CASE
                       WHEN seller_offer.status = 'accepted' OR selected_match.id IS NOT NULL THEN br.buyer_phone
                       ELSE NULL
                   END AS buyer_phone_visible
            FROM buyer_requests br
            LEFT JOIN LATERAL (
                SELECT id, payload, status, created_at
                FROM marketplace_notification_events mne
                WHERE mne.request_id = br.id
                  AND mne.seller_id = $1
                  AND mne.event_type = 'buyer_request_created'
                ORDER BY mne.created_at DESC, mne.id DESC
                LIMIT 1
            ) route_event ON TRUE
            LEFT JOIN LATERAL (
                SELECT id, status, price_offer, message, created_at, updated_at
                FROM buyer_request_offers bro
                WHERE bro.request_id = br.id
                  AND bro.seller_id = $1
                ORDER BY
                    CASE bro.status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                    bro.updated_at DESC,
                    bro.id DESC
                LIMIT 1
            ) seller_offer ON TRUE
            LEFT JOIN LATERAL (
                SELECT id, status, matched_at
                FROM marketplace_matches mm
                WHERE mm.request_id = br.id
                  AND mm.seller_id = $1
                ORDER BY mm.matched_at DESC, mm.id DESC
                LIMIT 1
            ) selected_match ON TRUE
            LEFT JOIN LATERAL (
                SELECT (ARRAY_AGG(sla.action ORDER BY sla.updated_at DESC, sla.id DESC))[1] AS latest_action,
                       MAX(sla.updated_at) AS latest_action_at,
                       BOOL_OR(sla.action = 'viewed') AS has_viewed,
                       BOOL_OR(sla.action = 'offered') AS has_offered,
                       BOOL_OR(sla.action = 'declined') AS has_declined,
                       BOOL_OR(sla.action = 'skipped') AS has_skipped
                FROM seller_lead_actions sla
                WHERE sla.request_id = br.id
                  AND sla.seller_id = $1
            ) actions ON TRUE
            WHERE br.entity_type = 'marketplace_request'
              AND (
                  route_event.id IS NOT NULL
                  OR actions.latest_action IS NOT NULL
                  OR seller_offer.id IS NOT NULL
                  OR selected_match.id IS NOT NULL
              )
        ), classified AS (
            SELECT request_id,
                   COALESCE(vehicle_title, category, request_type, 'Marketplace заявка') AS title,
                   city, category, brand, model, description, urgency, marketplace_status, created_at,
                   CASE
                       WHEN offer_status = 'accepted' OR selected_match_id IS NOT NULL THEN 'selected'
                       WHEN has_declined THEN 'declined'
                       WHEN has_skipped THEN 'skipped'
                       WHEN offer_status = 'pending' THEN 'replied'
                       WHEN has_viewed AND offer_id IS NULL AND NOT has_declined AND NOT has_skipped THEN 'in_work'
                       ELSE 'new'
                   END AS seller_status,
                   offer_status, price_offer, offer_message,
                   routed_match_score AS match_score,
                   routed_match_reasons AS match_reasons,
                   buyer_phone_visible,
                   GREATEST(
                       created_at,
                       COALESCE(offer_created_at, created_at),
                       COALESCE(latest_action_at, created_at),
                       COALESCE(selected_matched_at, created_at)
                   ) AS sort_at
            FROM relevant_leads
            WHERE CASE $2
                WHEN 'new' THEN route_event_id IS NOT NULL
                    AND offer_id IS NULL
                    AND NOT has_viewed
                    AND NOT has_offered
                    AND NOT has_declined
                    AND NOT has_skipped
                WHEN 'in_work' THEN has_viewed
                    AND offer_id IS NULL
                    AND NOT has_declined
                    AND NOT has_skipped
                WHEN 'replied' THEN offer_status = 'pending'
                WHEN 'selected' THEN offer_status = 'accepted' OR selected_match_id IS NOT NULL
                WHEN 'declined' THEN has_declined
                WHEN 'skipped' THEN has_skipped
                ELSE FALSE
            END
        )
        SELECT request_id, title, city, category, brand, model, description, urgency,
               marketplace_status, created_at, seller_status, offer_status, price_offer,
               offer_message, match_score, match_reasons, buyer_phone_visible
        FROM classified
        ORDER BY sort_at DESC, request_id DESC
        LIMIT $3 OFFSET $4
        """,
        seller_id,
        normalized_status,
        normalized_limit,
        normalized_offset,
    )


def _json_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, tuple):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return _json_list(parsed)
    return []


def _lead_timeline_label(source: str | None, action: str | None, status: str | None = None) -> str:
    labels = {
        "request": {"created": "Заявку створено"},
        "seller_action": {
            "viewed": "Продавець переглянув заявку",
            "offered": "Продавець відповів через Telegram",
            "declined": "Заявку відхилено продавцем",
            "skipped": "Заявку пропущено продавцем",
        },
        "offer": {"created": "Пропозицію надіслано покупцю"},
        "marketplace": {"selected": "Покупець обрав продавця"},
        "notification": {"buyer_request_created": "Telegram-сповіщення про заявку"},
    }
    label = labels.get(source or "", {}).get(action or "", "Оновлення заявки")
    if source == "notification" and status:
        status_labels = {
            "sent": "доставлено",
            "pending": "очікує",
            "failed": "не доставлено",
            "cancelled": "скасовано",
        }
        label = f"{label} · {status_labels.get(status, status)}"
    return label


async def get_seller_crm_lead_detail(seller_id: int, request_id: int):
    """Return a seller-scoped CRM lead detail payload or None when inaccessible."""
    lead = await fetchrow(
        """
        WITH scoped AS (
            SELECT br.id AS request_id,
                   NULLIF(CONCAT_WS(' ', br.brand, br.model), '') AS vehicle_title,
                   br.request_type, br.category, br.brand, br.model, br.vin,
                   br.city, br.description, br.message, br.urgency,
                   br.marketplace_status, br.created_at,
                   route_event.id AS route_event_id,
                   any_notification.id AS notification_event_id,
                   CASE
                       WHEN (route_event.payload->>'score') ~ '^[0-9]+$'
                       THEN (route_event.payload->>'score')::int
                       ELSE NULL
                   END AS match_score,
                   route_event.payload->'reasons' AS match_reasons,
                   seller_offer.id AS offer_id,
                   seller_offer.price_offer,
                   seller_offer.message AS offer_message,
                   seller_offer.status AS offer_status,
                   seller_offer.created_at AS offer_created_at,
                   selected_match.id AS selected_match_id,
                   selected_match.status AS selected_match_status,
                   selected_match.matched_at AS selected_at,
                   actions.viewed_at,
                   actions.responded_at,
                   actions.declined_at,
                   actions.skipped_at,
                   COALESCE(actions.has_viewed, FALSE) AS has_viewed,
                   COALESCE(actions.has_offered, FALSE) AS has_offered,
                   COALESCE(actions.has_declined, FALSE) AS has_declined,
                   COALESCE(actions.has_skipped, FALSE) AS has_skipped,
                   CASE
                       WHEN seller_offer.status = 'accepted' OR selected_match.id IS NOT NULL THEN br.buyer_name
                       ELSE NULL
                   END AS buyer_name_visible,
                   CASE
                       WHEN seller_offer.status = 'accepted' OR selected_match.id IS NOT NULL THEN br.buyer_phone
                       ELSE NULL
                   END AS buyer_phone_visible,
                   CASE
                       WHEN seller_offer.status = 'accepted' OR selected_match.id IS NOT NULL THEN br.buyer_telegram
                       ELSE NULL
                   END AS buyer_telegram_visible
            FROM buyer_requests br
            LEFT JOIN LATERAL (
                SELECT id, payload, status, created_at
                FROM marketplace_notification_events mne
                WHERE mne.request_id = br.id
                  AND mne.seller_id = $1
                  AND mne.event_type = 'buyer_request_created'
                ORDER BY mne.created_at DESC, mne.id DESC
                LIMIT 1
            ) route_event ON TRUE
            LEFT JOIN LATERAL (
                SELECT id
                FROM marketplace_notification_events mne
                WHERE mne.request_id = br.id
                  AND mne.seller_id = $1
                ORDER BY mne.created_at DESC, mne.id DESC
                LIMIT 1
            ) any_notification ON TRUE
            LEFT JOIN LATERAL (
                SELECT id, status, price_offer, message, created_at, updated_at
                FROM buyer_request_offers bro
                WHERE bro.request_id = br.id
                  AND bro.seller_id = $1
                ORDER BY
                    CASE bro.status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                    bro.updated_at DESC,
                    bro.id DESC
                LIMIT 1
            ) seller_offer ON TRUE
            LEFT JOIN LATERAL (
                SELECT id, status, matched_at
                FROM marketplace_matches mm
                WHERE mm.request_id = br.id
                  AND mm.seller_id = $1
                ORDER BY mm.matched_at DESC, mm.id DESC
                LIMIT 1
            ) selected_match ON TRUE
            LEFT JOIN LATERAL (
                SELECT MAX(sla.updated_at) FILTER (WHERE sla.action = 'viewed') AS viewed_at,
                       MAX(sla.updated_at) FILTER (WHERE sla.action = 'offered') AS responded_at,
                       MAX(sla.updated_at) FILTER (WHERE sla.action = 'declined') AS declined_at,
                       MAX(sla.updated_at) FILTER (WHERE sla.action = 'skipped') AS skipped_at,
                       BOOL_OR(sla.action = 'viewed') AS has_viewed,
                       BOOL_OR(sla.action = 'offered') AS has_offered,
                       BOOL_OR(sla.action = 'declined') AS has_declined,
                       BOOL_OR(sla.action = 'skipped') AS has_skipped
                FROM seller_lead_actions sla
                WHERE sla.request_id = br.id
                  AND sla.seller_id = $1
            ) actions ON TRUE
            WHERE br.id = $2
              AND br.entity_type = 'marketplace_request'
              AND (
                  route_event.id IS NOT NULL
                  OR any_notification.id IS NOT NULL
                  OR actions.has_viewed
                  OR actions.has_offered
                  OR actions.has_declined
                  OR actions.has_skipped
                  OR seller_offer.id IS NOT NULL
                  OR selected_match.id IS NOT NULL
              )
            LIMIT 1
        )
        SELECT *,
               CASE
                   WHEN offer_status = 'accepted' OR selected_match_id IS NOT NULL THEN 'selected'
                   WHEN has_declined THEN 'declined'
                   WHEN has_skipped THEN 'skipped'
                   WHEN offer_status = 'pending' OR has_offered THEN 'replied'
                   WHEN has_viewed THEN 'in_work'
                   ELSE 'new'
               END AS seller_status
        FROM scoped
        """,
        seller_id,
        request_id,
    )
    if not lead:
        return None

    timeline_rows = await fetch(
        """
        SELECT * FROM (
            SELECT br.created_at,
                   'request' AS source,
                   'created' AS action,
                   NULL::text AS status
            FROM buyer_requests br
            WHERE br.id = $2
              AND br.entity_type = 'marketplace_request'
            UNION ALL
            SELECT mne.created_at,
                   'notification' AS source,
                   mne.event_type AS action,
                   mne.status
            FROM marketplace_notification_events mne
            WHERE mne.request_id = $2
              AND mne.seller_id = $1
            UNION ALL
            SELECT sla.updated_at AS created_at,
                   'seller_action' AS source,
                   sla.action,
                   NULL::text AS status
            FROM seller_lead_actions sla
            WHERE sla.request_id = $2
              AND sla.seller_id = $1
            UNION ALL
            SELECT bro.created_at,
                   'offer' AS source,
                   'created' AS action,
                   bro.status
            FROM buyer_request_offers bro
            WHERE bro.request_id = $2
              AND bro.seller_id = $1
            UNION ALL
            SELECT mm.matched_at AS created_at,
                   'marketplace' AS source,
                   'selected' AS action,
                   mm.status
            FROM marketplace_matches mm
            WHERE mm.request_id = $2
              AND mm.seller_id = $1
        ) timeline
        WHERE created_at IS NOT NULL
        ORDER BY created_at ASC
        """,
        seller_id,
        request_id,
    )

    lead_data = dict(lead)
    buyer_contact = {
        "name": lead_data.get("buyer_name_visible"),
        "phone": lead_data.get("buyer_phone_visible"),
        "telegram": lead_data.get("buyer_telegram_visible"),
    }
    buyer_contact = {key: value for key, value in buyer_contact.items() if value}
    offer = None
    if lead_data.get("offer_id"):
        offer = {
            "offer_id": lead_data["offer_id"],
            "price": lead_data.get("price_offer"),
            "comment": lead_data.get("offer_message"),
            "status": lead_data.get("offer_status"),
            "created_at": lead_data.get("offer_created_at"),
        }

    return {
        "request": {
            "request_id": lead_data["request_id"],
            "title": lead_data.get("vehicle_title") or lead_data.get("category") or lead_data.get("request_type") or "Marketplace заявка",
            "category": lead_data.get("category"),
            "brand": lead_data.get("brand"),
            "model": lead_data.get("model"),
            "vin": lead_data.get("vin"),
            "city": lead_data.get("city"),
            "description": lead_data.get("description") or lead_data.get("message"),
            "urgency": lead_data.get("urgency"),
            "created_at": lead_data.get("created_at"),
            "buyer_contact": buyer_contact,
            "match_score": lead_data.get("match_score"),
            "match_reasons": _json_list(lead_data.get("match_reasons")),
        },
        "seller_state": {
            "seller_status": lead_data.get("seller_status"),
            "viewed_at": lead_data.get("viewed_at"),
            "responded_at": lead_data.get("responded_at"),
            "declined_at": lead_data.get("declined_at"),
            "skipped_at": lead_data.get("skipped_at"),
        },
        "offer": offer,
        "marketplace": {
            "selected_seller": bool(lead_data.get("selected_match_id")),
            "selected_at": lead_data.get("selected_at"),
            "is_selected": bool(lead_data.get("selected_match_id")) or lead_data.get("offer_status") == "accepted",
            "status": lead_data.get("marketplace_status"),
        },
        "timeline": [
            {
                "created_at": row["created_at"],
                "source": row["source"],
                "label": _lead_timeline_label(row["source"], row["action"], row["status"]),
            }
            for row in timeline_rows
        ],
    }


async def list_seller_crm_marketplace_activity(seller_id: int, limit: int = 12):
    normalized_limit = max(1, min(int(limit or 12), 30))
    return await fetch(
        """
        SELECT * FROM (
            SELECT mne.created_at,
                   'notification' AS source,
                   mne.event_type AS action,
                   mne.status,
                   mne.request_id,
                   mne.offer_id,
                   br.city,
                   br.category,
                   br.brand,
                   br.model,
                   br.description
            FROM marketplace_notification_events mne
            LEFT JOIN buyer_requests br ON br.id = mne.request_id
            WHERE mne.seller_id = $1
            UNION ALL
            SELECT sla.updated_at AS created_at,
                   'seller_action' AS source,
                   sla.action,
                   NULL::text AS status,
                   sla.request_id,
                   NULL::int AS offer_id,
                   br.city,
                   br.category,
                   br.brand,
                   br.model,
                   br.description
            FROM seller_lead_actions sla
            LEFT JOIN buyer_requests br ON br.id = sla.request_id
            WHERE sla.seller_id = $1
        ) activity
        ORDER BY created_at DESC
        LIMIT $2
        """,
        seller_id,
        normalized_limit,
    )


async def list_seller_crm_leads(seller_id: int, limit: int = 20):
    return await fetch(
        """
        SELECT id, name, phone, message, status, COALESCE(utm_source, referrer, 'direct') AS source, created_at
        FROM site_leads
        WHERE seller_id = $1
        ORDER BY created_at DESC, id DESC
        LIMIT $2
        """,
        seller_id,
        limit,
    )


async def list_seller_crm_cars(seller_id: int, limit: int = 20):
    return await fetch(
        """
        SELECT sc.id, b.name AS brand, m.name AS model, sc.views, sc.phone_clicks, sc.site_clicks, sc.created_at
        FROM seller_cars sc
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.seller_id = $1
        ORDER BY sc.created_at DESC, sc.id DESC
        LIMIT $2
        """,
        seller_id,
        limit,
    )


async def list_seller_crm_services(seller_id: int, limit: int = 20):
    return await fetch(
        """
        SELECT sv.id, sv.title, sv.category, COALESCE(st.views, 0) AS views,
               COALESCE(st.calls, 0) AS calls, COALESCE(st.clicks, 0) AS clicks
        FROM services sv
        LEFT JOIN service_stats st ON st.service_id = sv.id
        WHERE sv.seller_id = $1
        ORDER BY sv.created_at DESC, sv.id DESC
        LIMIT $2
        """,
        seller_id,
        limit,
    )


async def list_seller_crm_sources(seller_id: int, limit: int = 6):
    return await fetch(
        """
        SELECT COALESCE(NULLIF(a.utm_source, ''), 'direct') AS source, COUNT(*)::int AS visits
        FROM analytics_sessions a
        JOIN seller_sites ss ON ss.seller_id = $1 AND (ss.id = a.seller_site_id OR lower(ss.subdomain) = lower(a.subdomain))
        GROUP BY 1
        ORDER BY visits DESC, source ASC
        LIMIT $2
        """,
        seller_id,
        limit,
    )
