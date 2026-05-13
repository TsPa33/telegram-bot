from datetime import datetime, timedelta

from bot.database.base import fetchrow, execute
from bot.database.repositories.seller_repo import get_or_create_seller
from bot.database.repositories.site_repo import create_site, get_site_by_seller, subdomain_exists
from bot.services.site_config import get_default_site_config
from bot.utils.subdomain import generate_unique_subdomain

START_PROMO_CODE = "START"
START_PROMO_DAYS = 90


async def get_promo_activation(telegram_id: int, promo_code: str):
    return await fetchrow(
        """
        SELECT *
        FROM promo_activations
        WHERE telegram_id = $1
          AND promo_code = $2
        LIMIT 1
        """,
        telegram_id,
        promo_code.upper(),
    )


async def create_promo_activation(telegram_id: int, promo_code: str, expires_at):
    promo_code = promo_code.upper()

    row = await fetchrow(
        """
        INSERT INTO promo_activations (telegram_id, promo_code, expires_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id, promo_code) DO NOTHING
        RETURNING *
        """,
        telegram_id,
        promo_code,
        expires_at,
    )

    if row:
        return row

    return await get_promo_activation(telegram_id, promo_code)


async def activate_start_promo(telegram_id: int, username: str | None = None):
    expires_at = datetime.utcnow() + timedelta(days=START_PROMO_DAYS)
    activation = await create_promo_activation(
        telegram_id=telegram_id,
        promo_code=START_PROMO_CODE,
        expires_at=expires_at,
    )

    seller = await get_or_create_seller(telegram_id, username)

    await execute(
        """
        UPDATE sellers
        SET has_site = TRUE
        WHERE id = $1
          AND has_site IS NOT TRUE
        """,
        seller["id"],
    )

    site = await get_site_by_seller(seller["id"])
    if not site:
        subdomain = await generate_unique_subdomain(
            base=f"user{seller['id']}",
            exists_func=subdomain_exists,
        )
        site = await create_site(
            seller_id=seller["id"],
            subdomain=subdomain,
            config=get_default_site_config(),
        )

    return activation
