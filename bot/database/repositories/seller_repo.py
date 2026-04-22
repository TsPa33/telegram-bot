from bot.database.base import fetchrow, execute, fetch


# ================= SELLER =================

async def get_or_create_seller(telegram_id: int, username: str):
    seller = await fetchrow("""
        INSERT INTO sellers (telegram_id, username)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id)
        DO UPDATE SET username = COALESCE(EXCLUDED.username, sellers.username)
        RETURNING *
    """, telegram_id, username)

    await execute(
        """
        INSERT INTO seller_subscriptions (seller_id, slots, expires_at)
        SELECT $1, 1, NOW() + INTERVAL '30 days'
        WHERE NOT EXISTS (
            SELECT 1 FROM seller_subscriptions WHERE seller_id = $1
        )
        """,
        seller["id"],
    )

    return seller


async def get_seller_by_telegram_id(telegram_id: int):
    return await fetchrow("""
        SELECT * FROM sellers WHERE telegram_id = $1
    """, telegram_id)


# ================= LIMITS =================

async def increment_used(seller_id: int):
    await execute("""
        UPDATE sellers
        SET cars_used = cars_used + 1
        WHERE id = $1
    """, seller_id)


async def add_slot(seller_id: int, slots: int = 1):
    await execute("""
        UPDATE sellers
        SET cars_limit = cars_limit + $2
        WHERE id = $1
    """, seller_id, slots)


async def has_available_slot(telegram_id: int) -> bool:
    seller = await fetchrow("""
        SELECT id
        FROM sellers
        WHERE telegram_id = $1
    """, telegram_id)

    if not seller:
        return True

    available_slots = await get_active_slots(seller["id"])

    used_slots_row = await fetchrow(
        """
        SELECT COUNT(*)::int AS used_slots
        FROM seller_cars
        WHERE seller_id = $1
        """,
        seller["id"],
    )
    used_slots = used_slots_row["used_slots"] if used_slots_row else 0

    return used_slots < available_slots


async def get_active_slots(seller_id: int) -> int:
    row = await fetchrow(
        """
        SELECT COALESCE(SUM(slots), 0)::int AS available_slots
        FROM seller_subscriptions
        WHERE seller_id = $1
          AND expires_at > NOW()
        """,
        seller_id,
    )
    return row["available_slots"] if row else 0


async def add_subscription(
    seller_id: int,
    slots: int,
    expires_at,
    payment_id: int | None = None,
):
    await execute(
        """
        INSERT INTO seller_subscriptions (seller_id, slots, expires_at, payment_id)
        VALUES ($1, $2, $3, $4)
        """,
        seller_id,
        slots,
        expires_at,
        payment_id,
    )


async def get_active_subscriptions(seller_id: int):
    return await fetch(
        """
        SELECT
            slots,
            created_at,
            expires_at
        FROM seller_subscriptions
        WHERE seller_id = $1
          AND expires_at > NOW()
        ORDER BY created_at DESC
        """,
        seller_id,
    )


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


# ================= PROFILE =================

async def update_shop_name(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET shop_name = $1 WHERE id = $2", value, seller_id)


async def update_name(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET name = $1 WHERE id = $2", value, seller_id)


async def update_phone(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET phone = $1 WHERE id = $2", value, seller_id)


async def update_website(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET website = $1 WHERE id = $2", value, seller_id)


async def update_city(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET city = $1 WHERE id = $2", value, seller_id)


async def update_description_profile(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET description = $1 WHERE id = $2", value, seller_id)


FIELD_UPDATE_MAP = {
    "shop_name": update_shop_name,
    "name": update_name,
    "phone": update_phone,
    "website": update_website,
    "city": update_city,
    "description": update_description_profile,
}


async def update_seller_field(seller_id: int, field: str, value: str | None):
    func = FIELD_UPDATE_MAP.get(field)

    if not func:
        return

    await func(seller_id, value)
