from datetime import datetime
import json
import logging

from bot.database.base import execute, fetch, fetchrow
from bot.domain.statuses import get_car_display_status

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


async def set_crm_password_hash_if_empty(account_id: int, password_hash: str):
    return await fetchrow(
        """
        UPDATE seller_crm_accounts
        SET password_hash = $2
        WHERE id = $1
          AND COALESCE(password_hash, '') = ''
        RETURNING *
        """,
        account_id,
        password_hash,
    )


async def set_crm_password_hash_for_verified_reset(account_id: int, password_hash: str):
    return await fetchrow(
        """
        UPDATE seller_crm_accounts
        SET password_hash = $2
        WHERE id = $1
        RETURNING *
        """,
        account_id,
        password_hash,
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
            password_hash = CASE
                WHEN COALESCE(seller_crm_accounts.password_hash, '') = ''
                THEN EXCLUDED.password_hash
                ELSE seller_crm_accounts.password_hash
            END,
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


async def get_seller_crm_public_profile(seller_id: int):
    return await fetchrow(
        """
        WITH car_counts AS (
            SELECT COUNT(*) FILTER (WHERE status::text IN ('active', '1', 'true', 'enabled', 'published'))::int AS active_cars_count
            FROM seller_cars
            WHERE seller_id = $1
        ), service_counts AS (
            SELECT COUNT(*)::int AS active_services_count
            FROM services
            WHERE seller_id = $1
        ), offer_counts AS (
            SELECT COUNT(*)::int AS offers_sent_count
            FROM buyer_request_offers
            WHERE seller_id = $1
        ), selected_offers AS (
            SELECT COUNT(DISTINCT offer_id)::int AS selected_offers_count
            FROM (
                SELECT bro.id AS offer_id
                FROM buyer_request_offers bro
                WHERE bro.seller_id = $1
                  AND bro.status = 'accepted'
                UNION
                SELECT mm.offer_id
                FROM marketplace_matches mm
                WHERE mm.seller_id = $1
                  AND mm.offer_id IS NOT NULL
            ) selected
        ), response_pairs AS (
            SELECT
                EXTRACT(EPOCH FROM (bro.created_at - COALESCE(route_event.created_at, br.created_at)))::int AS response_seconds,
                bro.created_at AS offer_created_at
            FROM buyer_request_offers bro
            JOIN buyer_requests br ON br.id = bro.request_id
            LEFT JOIN LATERAL (
                SELECT mne.created_at
                FROM marketplace_notification_events mne
                WHERE mne.seller_id = $1
                  AND mne.request_id = bro.request_id
                  AND mne.event_type = 'buyer_request_created'
                ORDER BY mne.created_at ASC, mne.id ASC
                LIMIT 1
            ) route_event ON TRUE
            WHERE bro.seller_id = $1
              AND bro.created_at >= COALESCE(route_event.created_at, br.created_at)
        ), response_summary AS (
            SELECT
                AVG(response_seconds)::int AS avg_response_seconds,
                MAX(offer_created_at) AS last_offer_at,
                COUNT(*)::int AS measured_responses
            FROM response_pairs
        )
        SELECT
            s.id AS seller_id,
            s.telegram_id,
            s.username,
            s.shop_name,
            s.name,
            s.phone,
            s.website,
            s.city,
            s.description,
            s.photo_id,
            COALESCE(s.is_verified, FALSE) AS is_verified,
            COALESCE(s.has_site, FALSE) AS has_site,
            COALESCE(s.crm_enabled, FALSE) AS crm_enabled,
            s.created_at,
            COALESCE(cc.active_cars_count, 0)::int AS active_cars_count,
            COALESCE(sc.active_services_count, 0)::int AS active_services_count,
            COALESCE(oc.offers_sent_count, 0)::int AS offers_sent_count,
            COALESCE(so.selected_offers_count, 0)::int AS selected_offers_count,
            jsonb_build_object(
                'avg_response_seconds', rs.avg_response_seconds,
                'last_offer_at', rs.last_offer_at,
                'measured_responses', COALESCE(rs.measured_responses, 0)
            ) AS response_activity
        FROM sellers s
        CROSS JOIN car_counts cc
        CROSS JOIN service_counts sc
        CROSS JOIN offer_counts oc
        CROSS JOIN selected_offers so
        CROSS JOIN response_summary rs
        WHERE s.id = $1
        LIMIT 1
        """,
        seller_id,
    )


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


async def get_seller_crm_analytics(seller_id: int, days: int = 30):
    normalized_days = max(1, min(int(days or 30), 365))
    return await fetchrow(
        """
        WITH bounds AS (
            SELECT NOW() - ($2::int * INTERVAL '1 day') AS since
        ), seller_site AS (
            SELECT id, subdomain
            FROM seller_sites
            WHERE seller_id = $1
            LIMIT 1
        ), routed AS (
            SELECT DISTINCT mne.request_id
            FROM marketplace_notification_events mne, bounds
            WHERE mne.seller_id = $1
              AND mne.request_id IS NOT NULL
              AND mne.event_type = 'buyer_request_created'
              AND mne.created_at >= bounds.since
        ), viewed AS (
            SELECT DISTINCT sla.request_id
            FROM seller_lead_actions sla, bounds
            WHERE sla.seller_id = $1
              AND sla.action = 'viewed'
              AND sla.updated_at >= bounds.since
        ), declined AS (
            SELECT DISTINCT sla.request_id
            FROM seller_lead_actions sla, bounds
            WHERE sla.seller_id = $1
              AND sla.action = 'declined'
              AND sla.updated_at >= bounds.since
        ), skipped AS (
            SELECT DISTINCT sla.request_id
            FROM seller_lead_actions sla, bounds
            WHERE sla.seller_id = $1
              AND sla.action = 'skipped'
              AND sla.updated_at >= bounds.since
        ), offers AS (
            SELECT bro.id, bro.request_id, bro.status, bro.created_at
            FROM buyer_request_offers bro, bounds
            WHERE bro.seller_id = $1
              AND bro.created_at >= bounds.since
        ), response_pairs AS (
            SELECT EXTRACT(EPOCH FROM (bro.created_at - COALESCE(route_event.created_at, br.created_at)))::int AS response_seconds
            FROM buyer_request_offers bro
            JOIN buyer_requests br ON br.id = bro.request_id
            LEFT JOIN LATERAL (
                SELECT mne.created_at
                FROM marketplace_notification_events mne
                WHERE mne.request_id = bro.request_id
                  AND mne.seller_id = bro.seller_id
                  AND mne.event_type = 'buyer_request_created'
                ORDER BY mne.created_at ASC, mne.id ASC
                LIMIT 1
            ) route_event ON TRUE
            CROSS JOIN bounds
            WHERE bro.seller_id = $1
              AND bro.created_at >= bounds.since
              AND bro.created_at >= COALESCE(route_event.created_at, br.created_at)
        ), car_counts AS (
            SELECT 
                COUNT(*) FILTER (
                    WHERE status::text IN ('active', '1', 'true', 'enabled', 'published')
                )::int AS active_cars,
                
                COALESCE(
                    SUM(views) FILTER (
                        WHERE status::text IN ('active', '1', 'true', 'enabled', 'published')
                   ),
                   0
                )::int AS car_views,    
                
                COALESCE(
                    SUM(phone_clicks) FILTER (
                        WHERE status::text IN ('active', '1', 'true', 'enabled', 'published')
                   ),
                   0
                )::int AS car_phone_clicks,
                
                COALESCE(
                    SUM(site_clicks) FILTER (
                        WHERE status::text IN ('active', '1', 'true', 'enabled', 'published')
                    ),
                    0
                )::int AS car_site_clicks
                
            FROM seller_cars
            WHERE seller_id = $1
        ), service_counts AS (
            SELECT COUNT(*)::int AS services_count,
                   COALESCE(SUM(st.views), 0)::int AS service_views,
                   COALESCE(SUM(st.calls + st.clicks), 0)::int AS service_clicks
            FROM services sv
            LEFT JOIN service_stats st ON st.service_id = sv.id
            WHERE sv.seller_id = $1
        ), site_sessions AS (
            SELECT COUNT(*)::int AS visits,
                   COALESCE(SUM(a.pages_viewed), 0)::int AS page_views
            FROM analytics_sessions a
            JOIN seller_site ss ON ss.id = a.seller_site_id OR lower(ss.subdomain) = lower(a.subdomain)
            CROSS JOIN bounds
            WHERE a.started_at >= bounds.since
        ), site_events AS (
            SELECT COUNT(*) FILTER (WHERE e.event_type = 'telegram_click')::int AS telegram_clicks,
                   COUNT(*) FILTER (WHERE e.event_type IN ('cta_click', 'phone_click', 'site_click'))::int AS cta_clicks
            FROM analytics_events e
            JOIN seller_site ss ON ss.id = e.seller_site_id OR lower(ss.subdomain) = lower(e.subdomain)
            CROSS JOIN bounds
            WHERE e.created_at >= bounds.since
        ), site_lead_counts AS (
            SELECT COUNT(*)::int AS leads
            FROM site_leads sl
            CROSS JOIN bounds
            WHERE sl.seller_id = $1
              AND sl.created_at >= bounds.since
        )
        SELECT
            $2::int AS days,
            EXISTS (SELECT 1 FROM seller_site) AS has_website,
            COALESCE((SELECT COUNT(*) FROM routed), 0)::int AS routed_requests,
            COALESCE((SELECT COUNT(*) FROM viewed), 0)::int AS viewed_requests,
            COALESCE((SELECT COUNT(*) FROM declined), 0)::int AS declined_requests,
            COALESCE((SELECT COUNT(*) FROM skipped), 0)::int AS skipped_requests,
            COALESCE((SELECT COUNT(*) FROM offers), 0)::int AS offers_sent,
            COALESCE((SELECT COUNT(*) FROM offers WHERE status = 'accepted'), 0)::int AS offers_selected,
            COALESCE((SELECT COUNT(*) FROM offers WHERE status = 'rejected'), 0)::int AS offers_rejected,
            CASE WHEN COALESCE((SELECT COUNT(*) FROM offers), 0) = 0 THEN 0
                 ELSE ROUND(((SELECT COUNT(*) FROM offers WHERE status = 'accepted')::numeric / NULLIF((SELECT COUNT(*) FROM offers)::numeric, 0)) * 100, 1)
            END AS selected_conversion_percent,
            (SELECT AVG(response_seconds)::int FROM response_pairs) AS average_response_seconds,
            COALESCE(cc.active_cars, 0)::int AS active_cars,
            COALESCE(cc.car_views, 0)::int AS car_views,
            COALESCE(cc.car_phone_clicks, 0)::int AS car_phone_clicks,
            COALESCE(cc.car_site_clicks, 0)::int AS car_site_clicks,
            COALESCE(sc.services_count, 0)::int AS services_count,
            COALESCE(sc.service_views, 0)::int AS service_views,
            COALESCE(sc.service_clicks, 0)::int AS service_clicks,
            COALESCE(ss.visits, 0)::int AS visits,
            COALESCE(ss.page_views, 0)::int AS page_views,
            COALESCE(slc.leads, 0)::int AS leads,
            COALESCE(se.telegram_clicks, 0)::int AS telegram_clicks,
            COALESCE(se.cta_clicks, 0)::int AS cta_clicks,
            CASE WHEN COALESCE(ss.visits, 0) = 0 THEN 0
                 ELSE ROUND((COALESCE(slc.leads, 0)::numeric / NULLIF(ss.visits::numeric, 0)) * 100, 1)
            END AS conversion_percent
        FROM car_counts cc
        CROSS JOIN service_counts sc
        CROSS JOIN site_sessions ss
        CROSS JOIN site_events se
        CROSS JOIN site_lead_counts slc
        """,
        seller_id,
        normalized_days,
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
                   accepted_offer.seller_id AS accepted_offer_seller_id,
                   actions.latest_action,
                   actions.latest_action_at,
                   COALESCE(actions.has_viewed, FALSE) AS has_viewed,
                   COALESCE(actions.has_offered, FALSE) AS has_offered,
                   COALESCE(actions.has_declined, FALSE) AS has_declined,
                   COALESCE(actions.has_skipped, FALSE) AS has_skipped,
                   CASE
                       WHEN seller_offer.status = 'accepted' OR selected_match.id IS NOT NULL OR accepted_offer.seller_id = $1 THEN br.buyer_phone
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
                  AND mm.status IN ('matched', 'contacted', 'closed')
                ORDER BY mm.matched_at DESC, mm.id DESC
                LIMIT 1
            ) selected_match ON TRUE
            LEFT JOIN LATERAL (
                SELECT id, seller_id, updated_at
                FROM buyer_request_offers bro
                WHERE bro.request_id = br.id
                  AND bro.status = 'accepted'
                ORDER BY bro.updated_at DESC, bro.id DESC
                LIMIT 1
            ) accepted_offer ON TRUE
            LEFT JOIN LATERAL (
                SELECT seller_id
                FROM marketplace_matches mm
                WHERE mm.request_id = br.id
                  AND mm.status IN ('matched', 'contacted', 'closed')
                ORDER BY mm.matched_at DESC, mm.id DESC
                LIMIT 1
            ) any_selected_match ON TRUE
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
                       WHEN offer_status = 'accepted' OR selected_match_id IS NOT NULL OR accepted_offer_seller_id = $1 THEN 'selected'
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
                   has_viewed, has_offered, has_declined, has_skipped,
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
               offer_message, match_score, match_reasons, buyer_phone_visible,
               has_viewed, has_offered, has_declined, has_skipped
        FROM classified
        ORDER BY sort_at DESC, request_id DESC
        LIMIT $3 OFFSET $4
        """,
        seller_id,
        normalized_status,
        normalized_limit,
        normalized_offset,
    )

async def seller_has_crm_lead_access(seller_id: int, request_id: int) -> bool:
    row = await fetchrow(
        """
        SELECT EXISTS (
            SELECT 1
            FROM buyer_requests br
            WHERE br.id = $2
              AND br.entity_type = 'marketplace_request'
              AND (
                  EXISTS (
                      SELECT 1
                      FROM marketplace_notification_events mne
                      WHERE mne.request_id = br.id
                        AND mne.seller_id = $1
                        AND mne.event_type = 'buyer_request_created'
                  )
                  OR EXISTS (
                      SELECT 1
                      FROM seller_lead_actions sla
                      WHERE sla.request_id = br.id
                        AND sla.seller_id = $1
                  )
                  OR EXISTS (
                      SELECT 1
                      FROM buyer_request_offers bro
                      WHERE bro.request_id = br.id
                        AND bro.seller_id = $1
                  )
                  OR EXISTS (
                      SELECT 1
                      FROM marketplace_matches mm
                      WHERE mm.request_id = br.id
                        AND mm.seller_id = $1
                  )
              )
        ) AS has_access
        """,
        seller_id,
        request_id,
    )
    return bool(row and row["has_access"])


async def list_seller_crm_offers(
    seller_id: int,
    status: str = "active",
    limit: int = 30,
    offset: int = 0,
):
    """Return seller-scoped CRM offer cards using existing marketplace statuses only."""
    allowed_statuses = {"active", "selected", "rejected", "all"}
    normalized_status = status if status in allowed_statuses else "active"
    normalized_limit = max(1, min(int(limit or 30), 100))
    normalized_offset = max(0, int(offset or 0))

    return await fetch(
        """
        WITH seller_offers AS (
            SELECT bro.id AS offer_id,
                   bro.request_id,
                   bro.price_offer,
                   bro.message AS offer_message,
                   bro.status AS offer_status,
                   bro.created_at,
                   bro.updated_at,
                   br.request_type,
                   br.category,
                   br.brand,
                   br.model,
                   br.city,
                   COALESCE(NULLIF(br.description, ''), br.message) AS request_description,
                   br.marketplace_status AS request_marketplace_status,
                   selected_match.matched_at AS buyer_selected_at,
                   selected_match.status AS match_status,
                   CASE
                       WHEN bro.status = 'accepted' OR selected_match.offer_id IS NOT NULL THEN TRUE
                       ELSE FALSE
                   END AS is_selected
            FROM buyer_request_offers bro
            JOIN buyer_requests br ON br.id = bro.request_id
            LEFT JOIN LATERAL (
                SELECT mm.offer_id, mm.status, mm.matched_at
                FROM marketplace_matches mm
                WHERE mm.seller_id = $1
                  AND mm.offer_id = bro.id
                ORDER BY mm.matched_at DESC, mm.id DESC
                LIMIT 1
            ) selected_match ON TRUE
            WHERE bro.seller_id = $1
              AND br.entity_type = 'marketplace_request'
        )
        SELECT offer_id,
               request_id,
               COALESCE(NULLIF(CONCAT_WS(' ', brand, model), ''), category, request_type, 'Marketplace заявка') AS request_title,
               city,
               category,
               brand,
               model,
               CASE
                   WHEN request_description IS NULL OR request_description = '' THEN NULL
                   WHEN length(request_description) > 150 THEN left(request_description, 147) || '…'
                   ELSE request_description
               END AS request_description_short,
               price_offer,
               offer_message,
               offer_status,
               is_selected,
               created_at,
               updated_at,
               buyer_selected_at,
               request_marketplace_status
        FROM seller_offers
        WHERE CASE
            WHEN $2 = 'active' THEN offer_status = 'pending'
            WHEN $2 = 'selected' THEN is_selected
            WHEN $2 = 'rejected' THEN offer_status = 'rejected'
            ELSE TRUE
        END
        ORDER BY COALESCE(updated_at, created_at) DESC, offer_id DESC
        LIMIT $3 OFFSET $4
        """,
        seller_id,
        normalized_status,
        normalized_limit,
        normalized_offset,
    )


async def get_seller_crm_offer_detail(seller_id: int, offer_id: int):
    """Return one seller-owned offer with request context and compact timeline."""
    row = await fetchrow(
        """
        SELECT bro.id AS offer_id,
               bro.request_id,
               bro.price_offer,
               bro.message AS offer_message,
               bro.status AS offer_status,
               bro.created_at AS offer_created_at,
               bro.updated_at AS offer_updated_at,
               COALESCE(NULLIF(CONCAT_WS(' ', br.brand, br.model), ''), br.category, br.request_type, 'Marketplace заявка') AS request_title,
               br.request_type,
               br.category,
               br.brand,
               br.model,
               br.city,
               COALESCE(NULLIF(br.description, ''), br.message) AS request_description,
               br.urgency,
               br.created_at AS request_created_at,
               br.marketplace_status AS request_marketplace_status,
               selected_match.status AS match_status,
               selected_match.matched_at AS selected_at,
               CASE
                   WHEN bro.status = 'accepted' OR selected_match.offer_id IS NOT NULL THEN TRUE
                   ELSE FALSE
               END AS is_selected,
               latest_notification.status AS notification_status,
               latest_notification.created_at AS notification_created_at,
               latest_notification.updated_at AS notification_updated_at
        FROM buyer_request_offers bro
        JOIN buyer_requests br ON br.id = bro.request_id
        LEFT JOIN LATERAL (
            SELECT mm.offer_id, mm.status, mm.matched_at
            FROM marketplace_matches mm
            WHERE mm.seller_id = $1
              AND mm.offer_id = bro.id
            ORDER BY mm.matched_at DESC, mm.id DESC
            LIMIT 1
        ) selected_match ON TRUE
        LEFT JOIN LATERAL (
            SELECT mne.status, mne.created_at, mne.updated_at
            FROM marketplace_notification_events mne
            WHERE mne.seller_id = $1
              AND (mne.offer_id = bro.id OR mne.request_id = bro.request_id)
            ORDER BY mne.created_at DESC, mne.id DESC
            LIMIT 1
        ) latest_notification ON TRUE
        WHERE bro.seller_id = $1
          AND bro.id = $2
          AND br.entity_type = 'marketplace_request'
        LIMIT 1
        """,
        seller_id,
        offer_id,
    )
    if not row:
        return None

    data = dict(row)
    timeline_rows = await fetch(
        """
        SELECT * FROM (
            SELECT bro.created_at,
                   'offer' AS source,
                   'created' AS action,
                   bro.status
            FROM buyer_request_offers bro
            WHERE bro.seller_id = $1
              AND bro.id = $2
            UNION ALL
            SELECT mm.matched_at AS created_at,
                   'marketplace' AS source,
                   'selected' AS action,
                   mm.status
            FROM marketplace_matches mm
            JOIN buyer_request_offers bro ON bro.id = mm.offer_id
            WHERE bro.seller_id = $1
              AND mm.seller_id = $1
              AND mm.offer_id = $2
            UNION ALL
            SELECT mne.created_at,
                   'notification' AS source,
                   mne.event_type AS action,
                   mne.status
            FROM marketplace_notification_events mne
            JOIN buyer_request_offers bro ON bro.id = $2
            WHERE bro.seller_id = $1
              AND mne.seller_id = $1
              AND (mne.offer_id = bro.id OR mne.request_id = bro.request_id)
        ) timeline
        WHERE created_at IS NOT NULL
        ORDER BY created_at ASC
        """,
        seller_id,
        offer_id,
    )

    def timeline_label(source: str | None, action: str | None, status: str | None = None) -> str:
        labels = {
            "offer": {"created": "Пропозицію надіслано покупцю"},
            "marketplace": {"selected": "Покупець обрав цю пропозицію"},
            "notification": {
                "buyer_offer_accepted": "Сповіщення про вибір покупця",
                "buyer_request_created": "Telegram-сповіщення по заявці",
            },
        }
        label = labels.get(source or "", {}).get(action or "", "Оновлення пропозиції")
        if source == "notification" and status:
            status_labels = {
                "sent": "доставлено",
                "pending": "очікує",
                "failed": "не доставлено",
                "cancelled": "скасовано",
            }
            label = f"{label} · {status_labels.get(status, status)}"
        return label

    return {
        "offer": {
            "offer_id": data["offer_id"],
            "price": data.get("price_offer"),
            "message": data.get("offer_message"),
            "status": data.get("offer_status"),
            "created_at": data.get("offer_created_at"),
            "updated_at": data.get("offer_updated_at"),
        },
        "request": {
            "request_id": data["request_id"],
            "title": data.get("request_title") or "Marketplace заявка",
            "city": data.get("city"),
            "category": data.get("category"),
            "brand": data.get("brand"),
            "model": data.get("model"),
            "description": data.get("request_description"),
            "urgency": data.get("urgency"),
            "created_at": data.get("request_created_at"),
            "marketplace_status": data.get("request_marketplace_status"),
        },
        "selection": {
            "is_selected": data.get("is_selected"),
            "selected_at": data.get("selected_at"),
            "match_status": data.get("match_status"),
            "notification_status": data.get("notification_status"),
            "notification_at": data.get("notification_updated_at") or data.get("notification_created_at"),
        },
        "timeline": [
            {
                "created_at": item["created_at"],
                "source": item["source"],
                "action": item["action"],
                "status": item["status"],
                "label": timeline_label(item["source"], item["action"], item["status"]),
            }
            for item in timeline_rows
        ],
    }


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
                   accepted_offer.id AS accepted_offer_id,
                   accepted_offer.seller_id AS accepted_offer_seller_id,
                   accepted_offer.updated_at AS accepted_offer_updated_at,
                   COALESCE(accepted_offer.seller_id, any_selected_match.seller_id) AS selected_seller_id,
                   actions.viewed_at,
                   actions.responded_at,
                   actions.declined_at,
                   actions.skipped_at,
                   COALESCE(actions.has_viewed, FALSE) AS has_viewed,
                   COALESCE(actions.has_offered, FALSE) AS has_offered,
                   COALESCE(actions.has_declined, FALSE) AS has_declined,
                   COALESCE(actions.has_skipped, FALSE) AS has_skipped,
                   CASE
                       WHEN seller_offer.status = 'accepted' OR selected_match.id IS NOT NULL OR accepted_offer.seller_id = $1 THEN br.buyer_name
                       ELSE NULL
                   END AS buyer_name_visible,
                   CASE
                       WHEN seller_offer.status = 'accepted' OR selected_match.id IS NOT NULL OR accepted_offer.seller_id = $1 THEN br.buyer_phone
                       ELSE NULL
                   END AS buyer_phone_visible,
                   CASE
                       WHEN seller_offer.status = 'accepted' OR selected_match.id IS NOT NULL OR accepted_offer.seller_id = $1 THEN br.buyer_telegram
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
                  AND mm.status IN ('matched', 'contacted', 'closed')
                ORDER BY mm.matched_at DESC, mm.id DESC
                LIMIT 1
            ) selected_match ON TRUE
            LEFT JOIN LATERAL (
                SELECT id, seller_id, updated_at
                FROM buyer_request_offers bro
                WHERE bro.request_id = br.id
                  AND bro.status = 'accepted'
                ORDER BY bro.updated_at DESC, bro.id DESC
                LIMIT 1
            ) accepted_offer ON TRUE
            LEFT JOIN LATERAL (
                SELECT seller_id
                FROM marketplace_matches mm
                WHERE mm.request_id = br.id
                  AND mm.status IN ('matched', 'contacted', 'closed')
                ORDER BY mm.matched_at DESC, mm.id DESC
                LIMIT 1
            ) any_selected_match ON TRUE
            LEFT JOIN LATERAL (
                SELECT seller_id, updated_at
                FROM buyer_request_offers bro
                WHERE bro.request_id = br.id
                  AND bro.status = 'accepted'
                ORDER BY bro.updated_at DESC, bro.id DESC
                LIMIT 1
            ) accepted_offer ON TRUE
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
                   WHEN offer_status = 'accepted' OR selected_match_id IS NOT NULL OR accepted_offer_seller_id = $1 THEN 'selected'
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
            "marketplace_status": lead_data.get("marketplace_status"),
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
            "has_viewed": bool(lead_data.get("has_viewed")),
            "has_offered": bool(lead_data.get("has_offered")),
            "has_declined": bool(lead_data.get("has_declined")),
            "has_skipped": bool(lead_data.get("has_skipped")),
        },
        "offer": offer,
        "marketplace": {
            "selected_seller": bool(lead_data.get("selected_match_id")) or lead_data.get("offer_status") == "accepted" or lead_data.get("accepted_offer_seller_id") == seller_id,
            "selected_seller_id": lead_data.get("selected_seller_id"),
            "selected_other_seller": bool(lead_data.get("selected_seller_id")) and int(lead_data.get("selected_seller_id")) != int(seller_id),
            "selected_at": lead_data.get("selected_at") or lead_data.get("accepted_offer_updated_at"),
            "is_selected": bool(lead_data.get("selected_match_id")) or lead_data.get("offer_status") == "accepted" or lead_data.get("accepted_offer_seller_id") == seller_id,
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


async def get_seller_crm_content_summary(seller_id: int):
    return await fetchrow(
        """
        WITH car_counts AS (
            SELECT
                COUNT(*) FILTER (WHERE status::text IN ('active', '1', 'true', 'enabled', 'published'))::int AS active_cars,
                COUNT(*) FILTER (
                    WHERE status::text IN ('active', '1', 'true', 'enabled', 'published')
                      AND COALESCE(NULLIF(photo_id, ''), '') = ''
                )::int AS cars_without_photo,
                COUNT(*) FILTER (
                    WHERE status::text IN ('active', '1', 'true', 'enabled', 'published')
                      AND COALESCE(NULLIF(BTRIM(description), ''), '') = ''
                )::int AS cars_without_description
            FROM seller_cars
            WHERE seller_id = $1
        ), service_counts AS (
            SELECT
                COUNT(*)::int AS active_services,
                COUNT(*) FILTER (WHERE COALESCE(NULLIF(BTRIM(description), ''), '') = '')::int AS services_without_description
            FROM services
            WHERE seller_id = $1
        ), garage AS (
            SELECT COALESCE(SUM(slots), 0)::int AS garage_slots_total
            FROM seller_subscriptions
            WHERE seller_id = $1
              AND expires_at > NOW()
        )
        SELECT
            COALESCE(cc.active_cars, 0)::int AS active_cars,
            COALESCE(cc.cars_without_photo, 0)::int AS cars_without_photo,
            COALESCE(cc.cars_without_description, 0)::int AS cars_without_description,
            COALESCE(sc.active_services, 0)::int AS active_services,
            COALESCE(sc.services_without_description, 0)::int AS services_without_description,
            COALESCE(g.garage_slots_total, 0)::int AS garage_slots_total,
            COALESCE(cc.active_cars, 0)::int AS garage_slots_used,
            GREATEST(COALESCE(g.garage_slots_total, 0) - COALESCE(cc.active_cars, 0), 0)::int AS garage_slots_free
        FROM car_counts cc
        CROSS JOIN service_counts sc
        CROSS JOIN garage g
        """,
        seller_id,
    )


async def _get_seller_cars_columns() -> dict[str, str]:
    rows = await fetch(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'seller_cars'
        """
    )
    return {row["column_name"]: row["data_type"] for row in rows}


def _clean_car_description(value: str | None) -> str | None:
    cleaned = (value or "").strip()[:2000]
    return cleaned or None


def _normalize_car_status_for_display(value) -> str:
    return get_car_display_status(value)["status"]


def _car_status_db_value(status: str, status_type: str | None):
    normalized = _normalize_car_status_for_display(status)
    active = normalized == "active"
    if status_type in {"integer", "bigint", "smallint"}:
        return 1 if active else 0
    if status_type == "boolean":
        return active
    return "active" if active else "inactive"


class SellerCrmGarageFullError(Exception):
    """Raised when a seller has no free garage slots for a new CRM car."""


async def seller_crm_car_supports_is_catalog() -> bool:
    columns = await _get_seller_cars_columns()
    return "is_catalog" in columns


async def create_seller_crm_car(
    seller_id: int,
    model_id: int,
    description: str | None,
    is_catalog: bool = False,
):
    columns = await _get_seller_cars_columns()
    insert_columns = ["seller_id", "model_id", "photo_id", "description"]
    args = [seller_id, model_id, None, _clean_car_description(description)]
    select_values = [f"${index}" for index in range(1, len(args) + 1)]

    if "status" in columns:
        args.append(_car_status_db_value("active", columns.get("status")))
        insert_columns.append("status")
        select_values.append(f"${len(args)}")

    for counter_column in ("views", "phone_clicks", "site_clicks"):
        if counter_column in columns:
            args.append(0)
            insert_columns.append(counter_column)
            select_values.append(f"${len(args)}")

    if "is_catalog" in columns:
        args.append(bool(is_catalog))
        insert_columns.append("is_catalog")
        select_values.append(f"${len(args)}")

    row = await fetchrow(
        f"""
        WITH lock AS (
            SELECT pg_advisory_xact_lock($1::bigint)
        ), garage AS (
            SELECT COALESCE(SUM(ss.slots), 0)::int AS slots_total
            FROM lock
            LEFT JOIN seller_subscriptions ss
              ON ss.seller_id = $1
             AND ss.expires_at > NOW()
        ), used AS (
            SELECT COUNT(sc.*)::int AS slots_used
            FROM lock
            LEFT JOIN seller_cars sc ON sc.seller_id = $1
        ), inserted AS (
            INSERT INTO seller_cars ({', '.join(insert_columns)})
            SELECT {', '.join(select_values)}
            WHERE (SELECT slots_total FROM garage) > (SELECT slots_used FROM used)
            RETURNING id
        )
        SELECT
            (SELECT id FROM inserted) AS id,
            (SELECT slots_total FROM garage) AS slots_total,
            (SELECT slots_used FROM used) AS slots_used
        """,
        *args,
    )
    row_data = dict(row) if row else {}
    if row_data.get("id"):
        return row

    slots_total = int(row_data.get("slots_total") or 0)
    slots_used = int(row_data.get("slots_used") or 0)
    if slots_total <= slots_used:
        raise SellerCrmGarageFullError("No free garage slots")

    return None


def _is_car_active_status(value) -> bool:
    return get_car_display_status(value)["is_active"]


def _prepare_seller_crm_car(row, *, has_is_catalog: bool) -> dict | None:
    if not row:
        return None
    car = dict(row)
    status_meta = get_car_display_status(car.get("status"))
    car["status_meta"] = status_meta
    car["status_label"] = status_meta["label"]
    car["status_class"] = status_meta["css_class"]
    car["is_active"] = status_meta["is_active"]
    car["has_is_catalog"] = has_is_catalog
    car["is_catalog"] = bool(car.get("is_catalog")) if has_is_catalog else False
    car["has_photo"] = bool(car.get("has_photo"))
    car["has_description"] = bool(car.get("has_description"))
    car["photo_is_url"] = isinstance(car.get("photo_id"), str) and car.get("photo_id", "").startswith(("http://", "https://"))
    completed = 2  # brand and model are immutable existing content.
    completed += 1 if car["has_description"] else 0
    completed += 1 if car["has_photo"] else 0
    completed += 1 if car["is_active"] else 0
    car["content_completeness"] = round((completed / 5) * 100)
    return car


async def get_seller_crm_car_detail(seller_id: int, car_id: int):
    columns = await _get_seller_cars_columns()
    has_is_catalog = "is_catalog" in columns
    is_catalog_select = "sc.is_catalog" if has_is_catalog else "FALSE AS is_catalog"
    row = await fetchrow(
        f"""
        SELECT
            sc.id AS car_id,
            sc.id,
            sc.seller_id,
            b.name AS brand,
            m.name AS model,
            sc.description,
            sc.photo_id,
            COALESCE(sc.views, 0)::int AS views,
            COALESCE(sc.phone_clicks, 0)::int AS phone_clicks,
            COALESCE(sc.site_clicks, 0)::int AS site_clicks,
            sc.status,
            {is_catalog_select},
            sc.created_at,
            (COALESCE(NULLIF(sc.photo_id, ''), '') <> '') AS has_photo,
            (COALESCE(NULLIF(BTRIM(sc.description), ''), '') <> '') AS has_description
        FROM seller_cars sc
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.id = $1
          AND sc.seller_id = $2
        LIMIT 1
        """,
        car_id,
        seller_id,
    )
    return _prepare_seller_crm_car(row, has_is_catalog=has_is_catalog)


async def update_seller_crm_car(
    seller_id: int,
    car_id: int,
    description: str | None,
    status: str | None,
    is_catalog: bool | None,
) -> bool:
    columns = await _get_seller_cars_columns()
    assignments = ["description = $1"]
    args = [_clean_car_description(description)]

    if "status" in columns and status:
        args.append(_car_status_db_value(status, columns.get("status")))
        assignments.append(f"status = ${len(args)}")

    if "is_catalog" in columns and is_catalog is not None:
        args.append(bool(is_catalog))
        assignments.append(f"is_catalog = ${len(args)}")

    args.extend([car_id, seller_id])
    row = await fetchrow(
        f"""
        UPDATE seller_cars
        SET {', '.join(assignments)}
        WHERE id = ${len(args) - 1}
          AND seller_id = ${len(args)}
        RETURNING id
        """,
        *args,
    )
    return row is not None


async def update_seller_crm_car_photo(seller_id: int, car_id: int, photo_id_or_url: str) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_cars
        SET photo_id = $1
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        photo_id_or_url,
        car_id,
        seller_id,
    )
    return row is not None


async def set_seller_crm_car_status(seller_id: int, car_id: int, status: str) -> bool:
    columns = await _get_seller_cars_columns()
    if "status" not in columns:
        return False
    row = await fetchrow(
        """
        UPDATE seller_cars
        SET status = $1
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        _car_status_db_value(status, columns.get("status")),
        car_id,
        seller_id,
    )
    return row is not None


async def list_seller_crm_cars_inventory(
    seller_id: int,
    limit: int = 50,
    offset: int = 0,
):
    normalized_limit = max(1, min(int(limit or 50), 100))
    normalized_offset = max(0, int(offset or 0))

    return await fetch(
        """
        SELECT
            sc.id AS car_id,
            b.name AS brand,
            m.name AS model,
            sc.description,
            sc.photo_id,
            COALESCE(sc.views, 0)::int AS views,
            COALESCE(sc.phone_clicks, 0)::int AS phone_clicks,
            COALESCE(sc.site_clicks, 0)::int AS site_clicks,
            sc.status,
            FALSE AS is_catalog,
            sc.created_at,
            (COALESCE(NULLIF(sc.photo_id, ''), '') <> '') AS has_photo,
            (COALESCE(NULLIF(BTRIM(sc.description), ''), '') <> '') AS has_description
        FROM seller_cars sc
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.seller_id = $1
        ORDER BY sc.created_at DESC, sc.id DESC
        LIMIT $2 OFFSET $3
        """,
        seller_id,
        normalized_limit,
        normalized_offset,
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


async def _get_services_status_column() -> str | None:
    row = await fetchrow(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'services'
          AND column_name IN ('is_active', 'status')
        ORDER BY CASE column_name WHEN 'is_active' THEN 1 ELSE 2 END
        LIMIT 1
        """
    )
    return row["column_name"] if row else None


async def list_seller_crm_services_inventory(
    seller_id: int,
    limit: int = 50,
    offset: int = 0,
):
    normalized_limit = max(1, min(int(limit or 50), 100))
    normalized_offset = max(0, int(offset or 0))
    status_column = await _get_services_status_column()
    if status_column:
        status_select = f""",
            sv.{status_column} AS status,
            (COALESCE(sv.{status_column}::text, 'active') IN ('active', '1', 'true', 'enabled', 'published')) AS is_active,
            TRUE AS status_supported,
            '{status_column}' AS status_field"""
    else:
        status_select = """,
            'active' AS status,
            TRUE AS is_active,
            FALSE AS status_supported,
            NULL::text AS status_field"""

    return await fetch(
        f"""
        SELECT
            sv.id AS service_id,
            sv.title,
            sv.title AS name,
            sv.category,
            sv.description,
            sv.price,
            sv.photo_id,
            sv.photo_id AS image,
            COALESCE(st.views, 0)::int AS views,
            COALESCE(st.calls, 0)::int AS calls,
            COALESCE(st.clicks, 0)::int AS clicks,
            sv.created_at,
            (COALESCE(NULLIF(BTRIM(sv.description), ''), '') <> '') AS has_description,
            (sv.price IS NOT NULL) AS has_price,
            (COALESCE(NULLIF(sv.photo_id, ''), '') <> '') AS has_photo,
            (
                ((COALESCE(NULLIF(BTRIM(sv.title), ''), '') <> '')::int)
                + ((COALESCE(NULLIF(BTRIM(sv.category), ''), '') <> '')::int)
                + ((COALESCE(NULLIF(BTRIM(sv.description), ''), '') <> '')::int)
                + ((sv.price IS NOT NULL)::int)
                + ((COALESCE(NULLIF(sv.photo_id, ''), '') <> '')::int)
            ) * 20 AS content_completeness
            {status_select}
        FROM services sv
        LEFT JOIN service_stats st ON st.service_id = sv.id
        WHERE sv.seller_id = $1
        ORDER BY sv.created_at DESC, sv.id DESC
        LIMIT $2 OFFSET $3
        """,
        seller_id,
        normalized_limit,
        normalized_offset,
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

async def get_seller_crm_settings_summary(seller_id: int):
    seller = await fetchrow(
        """
        SELECT
            s.id,
            s.telegram_id,
            s.username,
            s.phone,
            s.shop_name,
            s.name,
            s.website,
            s.city,
            s.has_site,
            s.crm_enabled,
            s.created_at AS account_created_at,
            sca.crm_slug,
            sca.is_active AS crm_account_active,
            sca.created_at AS crm_account_created_at
        FROM sellers s
        LEFT JOIN seller_crm_accounts sca ON sca.seller_id = s.id
        WHERE s.id = $1
        LIMIT 1
        """,
        seller_id,
    )
    if not seller:
        return None

    active_subscriptions = await fetch(
        """
        SELECT slots, created_at, expires_at, (payment_id IS NOT NULL) AS is_paid
        FROM seller_subscriptions
        WHERE seller_id = $1
          AND expires_at > NOW()
        ORDER BY expires_at DESC, created_at DESC
        """,
        seller_id,
    )
    used_slots_row = await fetchrow(
        """
        SELECT COUNT(*)::int AS used_slots
        FROM seller_cars
        WHERE seller_id = $1
        """,
        seller_id,
    )
    active_cars_row = await fetchrow(
        """
        SELECT COUNT(*)::int AS active_cars_count
        FROM seller_cars
        WHERE seller_id = $1
          AND status::text IN ('active', '1', 'true', 'enabled', 'published')
        """,
        seller_id,
    )
    crm_subscriptions = await fetch(
        """
        SELECT status, started_at, expires_at, created_at
        FROM seller_crm_subscriptions
        WHERE seller_id = $1
          AND status = 'active'
          AND expires_at > NOW()
        ORDER BY expires_at DESC, created_at DESC
        """,
        seller_id,
    )
    payments = await fetch(
        """
        SELECT amount, status, COALESCE(product_type, product) AS product, product_type, created_at
        FROM payments
        WHERE seller_id = $1
        ORDER BY created_at DESC, id DESC
        LIMIT 10
        """,
        seller_id,
    )
    site = await fetchrow(
        """
        SELECT subdomain, status, has_custom_domain, custom_domain, created_at, updated_at
        FROM seller_sites
        WHERE seller_id = $1
        LIMIT 1
        """,
        seller_id,
    )

    seller_data = dict(seller)
    site_data = dict(site) if site else None
    subscriptions = [dict(row) for row in active_subscriptions]
    active_garage_slots = sum(int(row.get("slots") or 0) for row in subscriptions) if subscriptions else None
    used_data = dict(used_slots_row) if used_slots_row else {}
    active_cars_data = dict(active_cars_row) if active_cars_row else {}
    used_garage_slots = int(used_data.get("used_slots") or 0)
    active_cars_count = int(active_cars_data.get("active_cars_count") or 0)

    paid_subscriptions = [row for row in subscriptions if row.get("is_paid")]

    return {
        "seller": seller_data,
        "crm_slug": seller_data.get("crm_slug"),
        "crm_enabled": bool(seller_data.get("crm_enabled")),
        "crm_account_status": "active" if seller_data.get("crm_account_active") and seller_data.get("crm_enabled") else "inactive",
        "account_created_at": seller_data.get("crm_account_created_at") or seller_data.get("account_created_at"),
        "active_garage_slots": active_garage_slots,
        "used_garage_slots": used_garage_slots if active_garage_slots is not None else active_cars_count,
        "free_garage_slots": max(active_garage_slots - used_garage_slots, 0) if active_garage_slots is not None else None,
        "active_cars_count": active_cars_count,
        "garage_slots_available": active_garage_slots is not None,
        "active_seller_subscriptions": subscriptions,
        "active_paid_seller_subscriptions": paid_subscriptions,
        "active_crm_subscriptions": [dict(row) for row in crm_subscriptions],
        "latest_payments": [dict(row) for row in payments],
        "site": site_data,
        "has_site": bool(site_data or seller_data.get("has_site") or seller_data.get("website")),
        "custom_domain": site_data.get("custom_domain") if site_data else None,
    }
