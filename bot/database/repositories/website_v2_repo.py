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


async def get_website_v2_by_id(seller_id: int, website_id: int):
    return await fetchrow("SELECT * FROM seller_websites_v2 WHERE id=$1 AND seller_id=$2", website_id, seller_id)


async def get_website_v2_by_subdomain(subdomain: str):
    return await fetchrow("SELECT * FROM seller_websites_v2 WHERE lower(trim(subdomain))=lower(trim($1))", normalize_subdomain(subdomain))


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
