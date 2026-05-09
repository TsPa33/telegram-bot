from bot.database.base import fetchrow, execute, fetch


# ================= SELLER =================

async def get_or_create_seller(telegram_id: int, username: str):
    """
    SAFE get_or_create:
    - гарантує 1 seller на telegram_id
    - не створює дублікати
    - не створює дублікати підписок
    """

    seller = await fetchrow("""
        INSERT INTO sellers (telegram_id, username)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id)
        DO UPDATE SET username = COALESCE(EXCLUDED.username, sellers.username)
        RETURNING *
    """, telegram_id, username)

    # 🔥 SAFE subscription create (idempotent)
    await execute("""
        INSERT INTO seller_subscriptions (seller_id, slots, expires_at)
        SELECT $1, 1, NOW() + INTERVAL '30 days'
        WHERE NOT EXISTS (
            SELECT 1 
            FROM seller_subscriptions 
            WHERE seller_id = $1
              AND expires_at > NOW()
        )
    """, seller["id"])

    return seller


async def get_seller_by_telegram_id(telegram_id: int):
    return await fetchrow("""
        SELECT * FROM sellers WHERE telegram_id = $1
    """, telegram_id)


# ================= GET BY ID =================

async def get_seller_by_id(seller_id: int):
    return await fetchrow("""
        SELECT *
        FROM sellers
        WHERE id = $1
        LIMIT 1
    """, seller_id)


# ================= SLOTS =================

async def get_active_slots(seller_id: int) -> int:
    row = await fetchrow("""
        SELECT COALESCE(SUM(slots), 0)::int AS total
        FROM seller_subscriptions
        WHERE seller_id = $1
          AND expires_at > NOW()
    """, seller_id)

    return row["total"] if row else 0


async def get_used_slots(seller_id: int) -> int:
    row = await fetchrow("""
        SELECT COUNT(*)::int AS total
        FROM seller_cars
        WHERE seller_id = $1
    """, seller_id)

    return row["total"] if row else 0


async def get_garage_info(seller_id: int):
    active = await get_active_slots(seller_id)
    used = await get_used_slots(seller_id)

    return {
        "used": used,
        "total": active,
        "free": max(active - used, 0)
    }


async def has_available_slot(telegram_id: int) -> bool:
    seller = await fetchrow("""
        SELECT id FROM sellers WHERE telegram_id = $1
    """, telegram_id)

    if not seller:
        return True

    info = await get_garage_info(seller["id"])
    return info["used"] < info["total"]


# ================= SUBSCRIPTIONS =================

async def add_subscription(
    seller_id: int,
    slots: int,
    expires_at,
    payment_id: int | None = None,
):
    await execute("""
        INSERT INTO seller_subscriptions (seller_id, slots, expires_at, payment_id)
        VALUES ($1, $2, $3, $4)
    """, seller_id, slots, expires_at, payment_id)


async def get_active_subscriptions(seller_id: int):
    return await fetch("""
        SELECT slots, created_at, expires_at
        FROM seller_subscriptions
        WHERE seller_id = $1
          AND expires_at > NOW()
        ORDER BY created_at DESC
    """, seller_id)


async def get_subscription_history(seller_id: int):
    return await fetch("""
        SELECT slots, created_at, expires_at
        FROM seller_subscriptions
        WHERE seller_id = $1
        ORDER BY created_at DESC
    """, seller_id)


# ================= CAR =================

async def add_seller_car(seller_id: int, model_id: int, photo_id: str, description: str):
    await execute("""
        INSERT INTO seller_cars (
            seller_id,
            model_id,
            photo_id,
            description,
            status,
            views,
            phone_clicks,
            site_clicks
        )
        VALUES ($1, $2, $3, $4, 'active', 0, 0, 0)
    """, seller_id, model_id, photo_id, description)


async def get_seller_cars_by_seller_id(seller_id: int):
    return await fetch("""
        SELECT 
            sc.id,
            m.name AS model,
            b.name AS brand,
            sc.description,
            sc.views,
            sc.phone_clicks,
            sc.site_clicks
        FROM seller_cars sc
        JOIN models m ON sc.model_id = m.id
        JOIN brands b ON m.brand_id = b.id
        WHERE sc.seller_id = $1
        ORDER BY sc.id DESC
    """, seller_id)


async def get_seller_cars(telegram_id: int):
    return await fetch("""
        SELECT 
            sc.id,
            m.name AS model,
            b.name AS brand,
            sc.description,
            sc.views,
            sc.phone_clicks,
            sc.site_clicks
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        JOIN brands b ON m.brand_id = b.id
        WHERE s.telegram_id = $1
        ORDER BY sc.id DESC
    """, telegram_id)


# ================= DELETE =================

async def delete_car(car_id: int, telegram_id: int):
    await execute("""
        DELETE FROM seller_cars sc
        USING sellers s
        WHERE sc.id = $1
          AND sc.seller_id = s.id
          AND s.telegram_id = $2
    """, car_id, telegram_id)


# ================= UPDATE =================

async def update_description(car_id: int, description: str, telegram_id: int):
    row = await fetchrow("""
        UPDATE seller_cars sc
        SET description = $1
        FROM sellers s
        WHERE sc.id = $2
          AND sc.seller_id = s.id
          AND s.telegram_id = $3
        RETURNING sc.id
    """, description, car_id, telegram_id)

    return row is not None


# ================= STATS =================

async def get_seller_stats(telegram_id: int):
    return await fetchrow("""
        SELECT 
            COUNT(sc.id) AS total_cars,
            COALESCE(SUM(sc.views), 0) AS total_views,
            COALESCE(SUM(sc.phone_clicks), 0) AS phone_clicks,
            COALESCE(SUM(sc.site_clicks), 0) AS site_clicks
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        WHERE s.telegram_id = $1
    """, telegram_id)


async def get_seller_rating(telegram_id: int):
    return await fetchrow("""
        SELECT 
            COALESCE(SUM(sc.views), 0) AS views,
            COALESCE(SUM(sc.phone_clicks), 0) AS phone,
            COALESCE(SUM(sc.site_clicks), 0) AS site
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        WHERE s.telegram_id = $1
    """, telegram_id)


# ================= DEMO ADMIN =================

async def create_demo_seller(telegram_id: int, username: str, title: str):
    return await fetchrow(
        """
        INSERT INTO sellers (telegram_id, username, shop_name, name)
        VALUES ($1, $2, $3, $3)
        ON CONFLICT (telegram_id)
        DO UPDATE SET
            username = EXCLUDED.username,
            shop_name = EXCLUDED.shop_name,
            name = EXCLUDED.name
        RETURNING *
        """,
        telegram_id,
        username,
        title,
    )


async def delete_seller_by_id(seller_id: int) -> bool:
    row = await fetchrow(
        """
        DELETE FROM sellers
        WHERE id = $1
        RETURNING id
        """,
        seller_id,
    )
    return row is not None
