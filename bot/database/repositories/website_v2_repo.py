import json

from bot.database.base import fetch, fetchrow, execute
from bot.services.domain_service import normalize_subdomain
from bot.services.website_v2_config import default_website_v2_config, normalize_website_v2_type, patch_website_v2_config


async def create_website_v2(seller_id: int, site_type: str, name: str, subdomain: str):
    normalized_type = normalize_website_v2_type(site_type)
    normalized_subdomain = normalize_subdomain(subdomain)
    config = default_website_v2_config(normalized_type)
    return await fetchrow(
        """
        INSERT INTO seller_websites_v2 (seller_id, site_type, name, subdomain, status, config_draft, config_live)
        VALUES ($1, $2, $3, $4, 'draft', $5::jsonb, $5::jsonb)
        RETURNING *
        """,
        seller_id,
        normalized_type,
        name.strip(),
        normalized_subdomain,
        json.dumps(config),
    )


async def list_websites_v2_by_seller(seller_id: int):
    return await fetch("SELECT * FROM seller_websites_v2 WHERE seller_id=$1 ORDER BY created_at DESC", seller_id)


async def seller_has_website_v2_creation_access(seller_id: int) -> bool:
    row = await fetchrow(
        """
        SELECT EXISTS (
            SELECT 1
            FROM payments p
            WHERE p.seller_id = $1
              AND p.status = 'success'
              AND (
                  COALESCE(p.product_type, p.product) = 'site_plus'
                  OR (
                      COALESCE(p.product_type, p.product) IN ('site', 'site_standard')
                      AND p.created_at >= NOW() - INTERVAL '1 year'
                  )
              )
        ) AS has_access
        """,
        seller_id,
    )
    return bool(row and row.get("has_access"))


async def get_website_v2_by_id(seller_id: int, website_id: int):
    return await fetchrow("SELECT * FROM seller_websites_v2 WHERE id=$1 AND seller_id=$2", website_id, seller_id)


async def get_website_v2_by_subdomain(subdomain: str):
    return await fetchrow("SELECT * FROM seller_websites_v2 WHERE lower(trim(subdomain))=lower(trim($1))", normalize_subdomain(subdomain))


async def list_published_websites_v2(site_type: str = "carpot_catalog"):
    return await fetch(
        """
        SELECT id, seller_id, subdomain, site_type, status, published_at, updated_at
        FROM seller_websites_v2
        WHERE status = 'published'
          AND site_type = $1
        ORDER BY published_at DESC NULLS LAST, id DESC
        """,
        site_type,
    )


async def list_websites_v2_dashboard(seller_id: int):
    return await fetch(
        """
        SELECT
            w.id,
            w.seller_id,
            w.site_type,
            w.name,
            w.subdomain,
            w.status,
            w.updated_at,
            w.published_at,
            COALESCE(l.total_leads_count, 0)::int AS total_leads_count,
            COALESCE(l.new_leads_count, 0)::int AS new_leads_count
        FROM seller_websites_v2 w
        LEFT JOIN (
            SELECT
                website_id,
                COUNT(*)::int AS total_leads_count,
                COUNT(*) FILTER (WHERE status = 'new')::int AS new_leads_count
            FROM seller_website_v2_leads
            WHERE seller_id = $1
            GROUP BY website_id
        ) l ON l.website_id = w.id
        WHERE w.seller_id = $1
        ORDER BY w.updated_at DESC NULLS LAST, w.id DESC
        """,
        seller_id,
    )


async def count_website_v2_leads_summary(seller_id: int):
    row = await fetchrow(
        """
        SELECT
            COUNT(*)::int AS total_leads_count,
            COUNT(*) FILTER (WHERE status = 'new')::int AS new_leads_count
        FROM seller_website_v2_leads
        WHERE seller_id = $1
        """,
        seller_id,
    )
    return dict(row) if row else {"total_leads_count": 0, "new_leads_count": 0}


async def list_recent_website_v2_leads_by_seller(seller_id: int, limit: int = 8):
    normalized_limit = max(1, min(int(limit or 8), 20))
    return await fetch(
        """
        SELECT
            l.*,
            w.name AS website_name,
            w.subdomain AS website_subdomain,
            w.site_type AS website_site_type
        FROM seller_website_v2_leads l
        JOIN seller_websites_v2 w ON w.id = l.website_id AND w.seller_id = l.seller_id
        WHERE l.seller_id = $1
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT $2
        """,
        seller_id,
        normalized_limit,
    )


async def update_website_v2_draft(website_id: int, patch: dict):
    row = await fetchrow("SELECT id, config_draft, site_type FROM seller_websites_v2 WHERE id=$1", website_id)
    if not row:
        return None
    merged = patch_website_v2_config(row.get("config_draft") or {}, patch)
    return await fetchrow(
        "UPDATE seller_websites_v2 SET config_draft=$2::jsonb, updated_at=NOW() WHERE id=$1 RETURNING *",
        website_id,
        json.dumps(merged),
    )


async def publish_website_v2(website_id: int):
    return await execute(
        "UPDATE seller_websites_v2 SET config_live=config_draft, status='published', published_at=NOW(), updated_at=NOW() WHERE id=$1",
        website_id,
    )


async def create_website_v2_lead(
    *,
    website_id: int,
    seller_id: int,
    lead_type: str,
    name: str | None,
    phone: str,
    message: str | None,
    vin: str | None,
    item_title: str | None,
):
    return await fetchrow(
        """
        INSERT INTO seller_website_v2_leads (
            website_id, seller_id, lead_type, name, phone, message, vin, item_title, status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'new')
        RETURNING *
        """,
        website_id,
        seller_id,
        lead_type,
        name,
        phone,
        message,
        vin,
        item_title,
    )


async def list_website_v2_leads(website_id: int, seller_id: int):
    return await fetch(
        """
        SELECT *
        FROM seller_website_v2_leads
        WHERE website_id = $1
          AND seller_id = $2
        ORDER BY created_at DESC, id DESC
        """,
        website_id,
        seller_id,
    )


async def count_website_v2_leads_by_website(website_id: int, seller_id: int):
    row = await fetchrow(
        """
        SELECT
            COUNT(*)::int AS total_leads_count,
            COUNT(*) FILTER (WHERE status = 'new')::int AS new_leads_count
        FROM seller_website_v2_leads
        WHERE website_id = $1
          AND seller_id = $2
        """,
        website_id,
        seller_id,
    )
    return dict(row) if row else {"total_leads_count": 0, "new_leads_count": 0}


async def count_website_v2_leads_by_seller(seller_id: int):
    rows = await fetch(
        """
        SELECT
            website_id,
            COUNT(*)::int AS total_leads_count,
            COUNT(*) FILTER (WHERE status = 'new')::int AS new_leads_count
        FROM seller_website_v2_leads
        WHERE seller_id = $1
        GROUP BY website_id
        """,
        seller_id,
    )
    return [dict(row) for row in rows]


async def get_website_v2_lead(lead_id: int, seller_id: int):
    return await fetchrow(
        """
        SELECT *
        FROM seller_website_v2_leads
        WHERE id = $1
          AND seller_id = $2
        LIMIT 1
        """,
        lead_id,
        seller_id,
    )


def _normalize_website_v2_lead_status(status: str) -> str:
    value = (status or "").strip().lower()
    if value not in {"new", "viewed", "processed", "archived"}:
        raise ValueError("invalid website v2 lead status")
    return value


async def update_website_v2_lead_status(lead_id: int, seller_id: int, status: str):
    normalized = _normalize_website_v2_lead_status(status)
    return await fetchrow(
        """
        UPDATE seller_website_v2_leads
        SET status = $3
        WHERE id = $1
          AND seller_id = $2
        RETURNING *
        """,
        lead_id,
        seller_id,
        normalized,
    )
