from bot.database.base import fetch, fetchrow, execute


async def create_site(seller_id: int, subdomain: str, config: dict):
    return await fetchrow(
        """
        INSERT INTO seller_sites (
            seller_id,
            subdomain,
            config_draft
        )
        VALUES ($1, $2, $3::jsonb)
        RETURNING *
        """,
        seller_id,
        subdomain,
        config,
    )


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


async def update_draft(seller_id: int, config: dict) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_sites
        SET config_draft = $1::jsonb
        WHERE seller_id = $2
        RETURNING id
        """,
        config,
        seller_id,
    )

    return row is not None


async def publish_site(seller_id: int):
    await execute(
        """
        UPDATE seller_sites
        SET config_live = config_draft,
            status = 'active'
        WHERE seller_id = $1
        """,
        seller_id,
    )


async def subdomain_exists(subdomain: str) -> bool:
    rows = await fetch(
        """
        SELECT 1
        FROM seller_sites
        WHERE subdomain = $1
        LIMIT 1
        """,
        subdomain,
    )

    return bool(rows)
