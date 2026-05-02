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
    for k, v in new.items():

        if isinstance(v, dict) and isinstance(old.get(k), dict):
            old[k] = _deep_merge(old[k], v)

        elif isinstance(v, list):
            old[k] = v

        else:
            old[k] = v

    return old


async def update_site_config(site_id: int, config: dict) -> bool:
    async with transaction() as conn:

        print("\n========== UPDATE START ==========")

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
            print("❌ NO CURRENT CONFIG")
            return False

        current_config = current.get("config_draft") or {}

        if isinstance(current_config, str):
            try:
                current_config = json.loads(current_config)
            except Exception:
                current_config = {}

        print("🔵 CURRENT CONFIG MODULES:")
        print(current_config.get("modules"))

        # ===== DEFAULT STRUCTURE =====
        merged = merge_with_default(current_config)

        print("🟢 AFTER merge_with_default:")
        print(merged.get("modules"))

        # ===== INCOMING =====
        incoming = config if isinstance(config, dict) else {}

        print("🟡 INCOMING RAW:")
        print(incoming)

        if "modules" in incoming:
            print("🚨 INCOMING HAS MODULES:")
            print(incoming.get("modules"))

        # 🔥 BLOCK modules
        if isinstance(incoming.get("modules"), dict):
            print("⛔ REMOVING MODULES FROM INCOMING")
            incoming.pop("modules")

        print("🟡 INCOMING AFTER CLEAN:")
        print(incoming)

        # ===== MERGE =====
        merged = _deep_merge(merged, incoming)

        print("🟣 AFTER DEEP MERGE:")
        print(merged.get("modules"))

        # ===== HARD STRUCTURE =====
        merged.setdefault("header", {})
        merged.setdefault("hero", {})
        merged["hero"].setdefault("banners", [])
        merged.setdefault("contacts", {})

        # ===== MODULES NORMALIZATION =====
        default_modules = merge_with_default({})["modules"]
        current_modules = merged.get("modules")

        if not isinstance(current_modules, dict):
            print("⚠️ MODULES NOT DICT → RESET")
            merged["modules"] = default_modules
        else:
            merged["modules"] = {
                key: bool(current_modules.get(key, True))
                for key in default_modules
            }

        print("🟢 FINAL MODULES BEFORE SAVE:")
        print(merged.get("modules"))

        # ===== SAVE =====
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

        print("========== UPDATE END ==========\n")

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
