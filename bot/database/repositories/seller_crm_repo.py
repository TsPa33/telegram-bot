from datetime import datetime

from bot.database.base import execute, fetch, fetchrow


async def create_crm_subscription(seller_id: int, payment_id: int, days: int = 30):
    return await fetchrow(
        """
        WITH updated_seller AS (
            UPDATE sellers
            SET crm_enabled = TRUE
            WHERE id = $1
            RETURNING id
        )
        INSERT INTO seller_crm_subscriptions (seller_id, payment_id, status, started_at, expires_at)
        SELECT $1, $2, 'active', NOW(), NOW() + ($3::text || ' days')::interval
        WHERE EXISTS (SELECT 1 FROM updated_seller)
          AND NOT EXISTS (
              SELECT 1 FROM seller_crm_subscriptions WHERE payment_id = $2
          )
        RETURNING *
        """,
        seller_id,
        payment_id,
        days,
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


async def get_crm_account_by_slug(crm_slug: str):
    return await fetchrow(
        """
        SELECT sca.*, s.telegram_id, s.username, s.shop_name, s.name, s.crm_enabled
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
