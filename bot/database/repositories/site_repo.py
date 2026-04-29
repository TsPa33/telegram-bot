import json

from bot.database.base import fetch, fetchrow, execute, transaction
from bot.services.site_config import merge_with_default


# ================= CREATE =================

async def create_site(seller_id: int, subdomain: str, config: dict):
    config = merge_with_default(config or {})

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


# ================= SAFE UPDATE =================

def _deep_merge(old: dict, new: dict):
    """
    FIXED VERSION:
    - dict → merge
    - list → FULL overwrite (щоб працювало видалення)
    """

    for k, v in new.items():

        # dict → рекурсивно merge
        if isinstance(v, dict) and isinstance(old.get(k), dict):
            old[k] = _deep_merge(old[k], v)

        # 🔥 СПИСКИ — ПОВНИЙ overwrite
        elif isinstance(v, list):
            old[k] = v

        # інше → replace
        else:
            old[k] = v

    return old


async def update_site_config(site_id: int, config: dict) -> bool:
    """
    PRODUCTION SAFE UPDATE:
    - transaction + FOR UPDATE
    - JSON safe parse
    - correct overwrite logic for lists
    """

    async with transaction() as conn:

        current = await conn.fetchrow(
            """
            SELECT config_draft
            FROM seller_sites
            WHERE id = $1
            FOR UPDATE
            """,
            site_id,
        )

        if not current:
            return False

        current_config = current.get("config_draft") or {}

        # safe parse
        if isinstance(current_config, str):
            try:
                current_config = json.loads(current_config)
            except Exception:
                current_config = {}

        # default structure
        merged = merge_with_default(current_config)

        # incoming config
        incoming = config if isinstance(config, dict) else {}

        # 🔥 правильний merge
        merged = _deep_merge(merged, incoming)

        # гарантія структури
        merged.setdefault("header", {})
        merged.setdefault("hero", {})
        merged["hero"].setdefault("banners", [])
        merged.setdefault("modules", {})
        merged.setdefault("contacts", {})

        row = await conn.fetchrow(
            """
            UPDATE seller_sites
            SET config_draft = $1::jsonb,
                config_live = $1::jsonb
            WHERE id = $2
            RETURNING id
            """,
            json.dumps(merged),
            site_id,
        )

        return row is not None


# ================= UPDATE DRAFT =================

async def update_draft(seller_id: int, config: dict) -> bool:
    site = await get_site_by_seller(seller_id)
    if not site:
        return False

    return await update_site_config(site["id"], config)


# ================= PUBLISH =================

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
