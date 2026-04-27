import json

from bot.database.base import fetch, fetchrow, execute


# ================= CREATE =================

async def create_site(seller_id: int, subdomain: str, config: dict):
    return await fetchrow(
        """
        INSERT INTO seller_sites (
            seller_id,
            subdomain,
            config_draft,
            config_live,
            status
        )
        VALUES ($1, $2, $3::jsonb, $3::jsonb, 'active')
        ON CONFLICT (seller_id)
        DO UPDATE SET
            subdomain = EXCLUDED.subdomain,
            config_draft = EXCLUDED.config_draft,
            config_live = EXCLUDED.config_draft
        RETURNING *
        """,
        seller_id,
        subdomain,
        json.dumps(config),
    )


# ================= GET =================

async def get_site_by_seller(seller_id: int):
    return await fetchrow(
        """
        SELECT *
        FROM seller_sites
        WHERE seller_id = $1
        LIMIT 1
        """,
        seller_id,
    )


async def get_site_by_subdomain(subdomain: str):
    return await fetchrow(
        """
        SELECT *
        FROM seller_sites
        WHERE subdomain = $1
        LIMIT 1
        """,
        subdomain,
    )


# ================= UPDATE (DRAFT) =================

async def update_draft(seller_id: int, config: dict) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_sites
        SET config_draft = $1::jsonb,
            config_live = $1::jsonb  -- 🔥 автопублікація
        WHERE seller_id = $2
        RETURNING id
        """,
        json.dumps(config),
        seller_id,
    )
    return row is not None


# ================= 🔥 UPDATE CONFIG (MAIN FIX) =================

async def update_site_config(site_id: int, config: dict) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_sites
        SET config_draft = $1::jsonb,
            config_live = $1::jsonb  -- 🔥 автопублікація
        WHERE id = $2
        RETURNING id
        """,
        json.dumps(config),
        site_id,
    )
    return row is not None


# ================= PUBLISH (МОЖНА ЗАЛИШИТИ) =================

async def publish_site(seller_id: int) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_sites
        SET config_live = config_draft,
            status = 'active'
        WHERE seller_id = $1
        RETURNING id
        """,
        seller_id,
    )
    return row is not None


# ================= SUBDOMAIN =================

async def subdomain_exists(subdomain: str) -> bool:
    row = await fetchrow(
        """
        SELECT 1
        FROM seller_sites
        WHERE subdomain = $1
        LIMIT 1
        """,
        subdomain,
    )
    return row is not None
