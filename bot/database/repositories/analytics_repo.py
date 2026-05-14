from __future__ import annotations

from datetime import date
from typing import Any

from bot.database.base import fetch, fetchrow


ALLOWED_ANALYTICS_EVENT_TYPES = {
    "page_view",
    "phone_click",
    "telegram_click",
    "whatsapp_click",
    "viber_click",
    "lead_submit",
    "callback_click",
    "service_order_click",
    "pricing_click",
    "gallery_open",
    "site_open",
    "demo_open",
}

CTA_EVENT_TYPES = {
    "phone_click",
    "telegram_click",
    "whatsapp_click",
    "viber_click",
    "callback_click",
    "service_order_click",
    "pricing_click",
}

DEMO_SUBDOMAINS = [
    "demo-sto",
    "demo-tow",
    "demo-shynomontag",
    "demo-parts",
    "demo-electric",
]


def _limit(value: str | None, max_length: int = 500) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    return value[:max_length]


def parse_start_source(start_param: str | None) -> tuple[str | None, str | None]:
    start_param = _limit(start_param, 200)
    if not start_param:
        return None, None

    parts = [part for part in start_param.split("_") if part]
    if not parts:
        return start_param, None

    source = parts[0].lower()
    campaign = "_".join(parts[1:]).lower() if len(parts) > 1 else None
    return source, campaign


async def upsert_session(
    *,
    session_id: str,
    seller_site_id: int | None = None,
    subdomain: str | None = None,
    landing_page: str | None = None,
    current_page: str | None = None,
    referrer: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    utm_content: str | None = None,
    utm_term: str | None = None,
    ip_address: str | None = None,
    country: str | None = None,
    city: str | None = None,
    device_type: str | None = None,
    browser: str | None = None,
    operating_system: str | None = None,
    language: str | None = None,
    user_agent: str | None = None,
    time_on_site_seconds: int = 0,
):
    return await fetchrow(
        """
        INSERT INTO analytics_sessions (
            session_id, seller_site_id, subdomain, landing_page, current_page,
            referrer, utm_source, utm_medium, utm_campaign, utm_content, utm_term,
            ip_address, country, city, device_type, browser, operating_system,
            language, user_agent, time_on_site_seconds, pages_viewed
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, 1)
        ON CONFLICT (session_id) DO UPDATE
        SET seller_site_id = COALESCE(EXCLUDED.seller_site_id, analytics_sessions.seller_site_id),
            subdomain = COALESCE(EXCLUDED.subdomain, analytics_sessions.subdomain),
            current_page = COALESCE(EXCLUDED.current_page, analytics_sessions.current_page),
            referrer = COALESCE(analytics_sessions.referrer, EXCLUDED.referrer),
            utm_source = COALESCE(analytics_sessions.utm_source, EXCLUDED.utm_source),
            utm_medium = COALESCE(analytics_sessions.utm_medium, EXCLUDED.utm_medium),
            utm_campaign = COALESCE(analytics_sessions.utm_campaign, EXCLUDED.utm_campaign),
            utm_content = COALESCE(analytics_sessions.utm_content, EXCLUDED.utm_content),
            utm_term = COALESCE(analytics_sessions.utm_term, EXCLUDED.utm_term),
            ip_address = COALESCE(EXCLUDED.ip_address, analytics_sessions.ip_address),
            country = COALESCE(EXCLUDED.country, analytics_sessions.country),
            city = COALESCE(EXCLUDED.city, analytics_sessions.city),
            device_type = COALESCE(EXCLUDED.device_type, analytics_sessions.device_type),
            browser = COALESCE(EXCLUDED.browser, analytics_sessions.browser),
            operating_system = COALESCE(EXCLUDED.operating_system, analytics_sessions.operating_system),
            language = COALESCE(EXCLUDED.language, analytics_sessions.language),
            user_agent = COALESCE(EXCLUDED.user_agent, analytics_sessions.user_agent),
            last_seen_at = NOW(),
            time_on_site_seconds = GREATEST(analytics_sessions.time_on_site_seconds, EXCLUDED.time_on_site_seconds),
            pages_viewed = analytics_sessions.pages_viewed + 1
        RETURNING *
        """,
        _limit(session_id, 120),
        seller_site_id,
        _limit(subdomain, 120),
        _limit(landing_page, 1000),
        _limit(current_page, 1000),
        _limit(referrer, 1000),
        _limit(utm_source, 200),
        _limit(utm_medium, 200),
        _limit(utm_campaign, 200),
        _limit(utm_content, 200),
        _limit(utm_term, 200),
        _limit(ip_address, 80),
        _limit(country, 120),
        _limit(city, 120),
        _limit(device_type, 40),
        _limit(browser, 120),
        _limit(operating_system, 120),
        _limit(language, 120),
        _limit(user_agent, 600),
        max(0, int(time_on_site_seconds or 0)),
    )


async def add_event(
    *,
    session_id: str,
    event_type: str,
    seller_site_id: int | None = None,
    subdomain: str | None = None,
    event_name: str | None = None,
    event_target: str | None = None,
    page_url: str | None = None,
):
    if event_type not in ALLOWED_ANALYTICS_EVENT_TYPES:
        raise ValueError("Invalid analytics event type")

    return await fetchrow(
        """
        INSERT INTO analytics_events (
            session_id, seller_site_id, subdomain, event_type, event_name, event_target, page_url
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        _limit(session_id, 120),
        seller_site_id,
        _limit(subdomain, 120),
        event_type,
        _limit(event_name, 200),
        _limit(event_target, 500),
        _limit(page_url, 1000),
    )


async def list_sessions(limit: int = 100):
    return await fetch(
        """
        SELECT *
        FROM analytics_sessions
        ORDER BY last_seen_at DESC, id DESC
        LIMIT $1
        """,
        min(max(int(limit), 1), 500),
    )


async def list_events(limit: int = 100):
    return await fetch(
        """
        SELECT e.*, COALESCE(s.utm_source, 'direct') AS source
        FROM analytics_events e
        LEFT JOIN analytics_sessions s ON s.session_id = e.session_id
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT $1
        """,
        min(max(int(limit), 1), 500),
    )


async def get_analytics_summary(day: date | None = None) -> dict[str, Any]:
    row = await fetchrow(
        """
        WITH bounds AS (
            SELECT COALESCE($1::date, CURRENT_DATE) AS day
        ), source_counts AS (
            SELECT COALESCE(NULLIF(utm_source, ''), 'direct') AS source, COUNT(*) AS sessions
            FROM analytics_sessions, bounds
            WHERE started_at >= bounds.day AND started_at < bounds.day + INTERVAL '1 day'
            GROUP BY 1
            ORDER BY sessions DESC, source ASC
            LIMIT 1
        )
        SELECT
            (SELECT COUNT(*) FROM analytics_sessions, bounds WHERE started_at >= bounds.day AND started_at < bounds.day + INTERVAL '1 day') AS visits_today,
            (SELECT COUNT(*) FROM site_leads, bounds WHERE created_at >= bounds.day AND created_at < bounds.day + INTERVAL '1 day') AS leads_today,
            (SELECT COUNT(*) FROM telegram_attribution, bounds WHERE created_at >= bounds.day AND created_at < bounds.day + INTERVAL '1 day') AS telegram_starts_today,
            (SELECT COUNT(*) FROM analytics_events, bounds WHERE created_at >= bounds.day AND created_at < bounds.day + INTERVAL '1 day' AND event_type = ANY($2::text[])) AS cta_clicks_today,
            (SELECT source FROM source_counts LIMIT 1) AS top_source_today
        """,
        day,
        list(CTA_EVENT_TYPES),
    )
    return dict(row or {})


async def get_source_summary(limit: int = 50):
    return await fetch(
        """
        WITH session_sources AS (
            SELECT COALESCE(NULLIF(utm_source, ''), 'direct') AS source, COUNT(*) AS sessions
            FROM analytics_sessions
            GROUP BY 1
        ), lead_sources AS (
            SELECT COALESCE(NULLIF(utm_source, ''), 'direct') AS source, COUNT(*) AS leads
            FROM site_leads
            GROUP BY 1
        ), telegram_sources AS (
            SELECT COALESCE(NULLIF(source, ''), 'direct') AS source, COUNT(*) AS telegram_starts
            FROM telegram_attribution
            GROUP BY 1
        ), phone_sources AS (
            SELECT COALESCE(NULLIF(s.utm_source, ''), 'direct') AS source, COUNT(*) AS phone_clicks
            FROM analytics_events e
            LEFT JOIN analytics_sessions s ON s.session_id = e.session_id
            WHERE e.event_type = 'phone_click'
            GROUP BY 1
        )
        SELECT
            COALESCE(ss.source, ls.source, ts.source, ps.source) AS source,
            COALESCE(ss.sessions, 0) AS sessions,
            COALESCE(ls.leads, 0) AS leads,
            COALESCE(ts.telegram_starts, 0) AS telegram_starts,
            COALESCE(ps.phone_clicks, 0) AS phone_clicks,
            CASE WHEN COALESCE(ss.sessions, 0) = 0 THEN 0
                 ELSE ROUND((COALESCE(ls.leads, 0)::numeric / ss.sessions::numeric) * 100, 2)
            END AS conversion_rate
        FROM session_sources ss
        FULL OUTER JOIN lead_sources ls ON ls.source = ss.source
        FULL OUTER JOIN telegram_sources ts ON ts.source = COALESCE(ss.source, ls.source)
        FULL OUTER JOIN phone_sources ps ON ps.source = COALESCE(ss.source, ls.source, ts.source)
        ORDER BY sessions DESC, leads DESC, source ASC
        LIMIT $1
        """,
        min(max(int(limit), 1), 200),
    )


async def get_demo_summary():
    return await fetch(
        """
        WITH demos AS (SELECT unnest($1::text[]) AS subdomain),
        views AS (
            SELECT subdomain, COUNT(*) AS views
            FROM analytics_events
            WHERE event_type IN ('page_view', 'demo_open', 'site_open')
            GROUP BY subdomain
        ), ctas AS (
            SELECT subdomain, COUNT(*) AS cta_clicks
            FROM analytics_events
            WHERE event_type = ANY($2::text[])
            GROUP BY subdomain
        ), leads AS (
            SELECT subdomain, COUNT(*) AS leads
            FROM site_leads
            GROUP BY subdomain
        ), telegram_clicks AS (
            SELECT subdomain, COUNT(*) AS telegram_clicks
            FROM analytics_events
            WHERE event_type = 'telegram_click'
            GROUP BY subdomain
        ), starts AS (
            SELECT normalized_subdomain AS subdomain, COUNT(*) AS telegram_starts
            FROM (
                SELECT
                    CASE
                        WHEN replace(COALESCE(start_param, ''), '_', '-') = ANY($1::text[]) THEN replace(start_param, '_', '-')
                        WHEN replace(COALESCE(campaign, ''), '_', '-') = ANY($1::text[]) THEN replace(campaign, '_', '-')
                        ELSE NULL
                    END AS normalized_subdomain
                FROM telegram_attribution
            ) raw_starts
            WHERE normalized_subdomain IS NOT NULL
            GROUP BY normalized_subdomain
        )
        SELECT
            demos.subdomain,
            COALESCE(views.views, 0) AS views,
            COALESCE(ctas.cta_clicks, 0) AS cta_clicks,
            COALESCE(leads.leads, 0) AS leads,
            COALESCE(telegram_clicks.telegram_clicks, 0) AS telegram_clicks,
            COALESCE(starts.telegram_starts, 0) AS telegram_starts
        FROM demos
        LEFT JOIN views ON views.subdomain = demos.subdomain
        LEFT JOIN ctas ON ctas.subdomain = demos.subdomain
        LEFT JOIN leads ON leads.subdomain = demos.subdomain
        LEFT JOIN telegram_clicks ON telegram_clicks.subdomain = demos.subdomain
        LEFT JOIN starts ON starts.subdomain = demos.subdomain
        ORDER BY demos.subdomain
        """,
        DEMO_SUBDOMAINS,
        list(CTA_EVENT_TYPES),
    )


async def upsert_telegram_attribution(
    *,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    language_code: str | None = None,
    start_param: str | None = None,
    source: str | None = None,
    campaign: str | None = None,
):
    parsed_source, parsed_campaign = parse_start_source(start_param)
    source = source or parsed_source
    campaign = campaign or parsed_campaign

    return await fetchrow(
        """
        WITH updated AS (
            UPDATE telegram_attribution
            SET username = COALESCE($2, username),
                first_name = COALESCE($3, first_name),
                language_code = COALESCE($4, language_code),
                start_param = COALESCE($5, start_param),
                source = COALESCE($6, source),
                campaign = COALESCE($7, campaign),
                last_seen_at = NOW()
            WHERE telegram_id = $1
            RETURNING *
        ), inserted AS (
            INSERT INTO telegram_attribution (
                telegram_id, username, first_name, language_code, start_param, source, campaign
            )
            SELECT $1, $2, $3, $4, $5, $6, $7
            WHERE NOT EXISTS (SELECT 1 FROM updated)
            RETURNING *
        )
        SELECT * FROM updated
        UNION ALL
        SELECT * FROM inserted
        LIMIT 1
        """,
        telegram_id,
        _limit(username, 120),
        _limit(first_name, 120),
        _limit(language_code, 40),
        _limit(start_param, 200),
        _limit(source, 120),
        _limit(campaign, 200),
    )
