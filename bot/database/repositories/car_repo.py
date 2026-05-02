from bot.database.base import fetch, fetchrow, execute


# ================= BASE SELECT =================

BASE_SELECT = """
    SELECT 
        sc.id,
        sc.photo_id,
        sc.description,
        sc.views,
        sc.phone_clicks,
        sc.site_clicks,
        sc.seller_id,

        m.name AS model,
        b.name AS brand,

        s.username,
        s.telegram_id,
        s.phone,
        s.name,
        s.city,
        s.shop_name,
        s.website,
        s.is_verified

    FROM seller_cars sc
    JOIN sellers s ON sc.seller_id = s.id
    JOIN models m ON sc.model_id = m.id
    JOIN brands b ON m.brand_id = b.id
"""


# ================= COUNT =================

async def count_cars(model_id: int) -> int:
    row = await fetchrow("""
        SELECT COUNT(*) as total
        FROM seller_cars
        WHERE model_id = $1
          AND status = 'active'
    """, model_id)

    return row["total"] if row else 0


# ================= GET FIRST =================

async def get_first_car(model_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status = 'active'
        ORDER BY sc.id DESC
        LIMIT 1
    """, model_id)


# ================= GET NEXT =================

async def get_next_car(model_id: int, last_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status = 'active'
          AND sc.id < $2
        ORDER BY sc.id DESC
        LIMIT 1
    """, model_id, last_id)


# ================= GET PREV =================

async def get_prev_car(model_id: int, current_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status = 'active'
          AND sc.id > $2
        ORDER BY sc.id ASC
        LIMIT 1
    """, model_id, current_id)


# ================= GET ONE =================

async def get_car_by_id(car_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.id = $1
    """, car_id)


# ================= SELLER CARS =================

async def get_seller_cars(telegram_id: int):
    return await fetch(f"""
        {BASE_SELECT}
        WHERE s.telegram_id = $1
        ORDER BY sc.id DESC
        LIMIT 20
    """, telegram_id)


async def get_cars_by_seller(seller_id: int):
    return await fetch("""
        SELECT
            sc.id,
            sc.photo_id,
            sc.description,
            sc.seller_id,
            m.name AS model,
            b.name AS brand
        FROM seller_cars sc
        JOIN models m ON sc.model_id = m.id
        JOIN brands b ON m.brand_id = b.id
        WHERE sc.seller_id = $1
          AND sc.status = 'active'
        ORDER BY sc.id DESC
    """, seller_id)


# ================= PAGINATION =================

async def get_cars_page(model_id: int, limit: int, offset: int):
    return await fetch(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status = 'active'
        ORDER BY sc.id DESC
        LIMIT $2 OFFSET $3
    """, model_id, limit, offset)


# ================= VIEW TRACK =================

async def add_unique_car_view(car_id: int, user_id: int) -> bool:
    row = await fetchrow("""
        WITH inserted AS (
            INSERT INTO car_views (car_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT (car_id, user_id) DO NOTHING
            RETURNING 1
        )
        UPDATE seller_cars
        SET views = views + 1
        WHERE id = $1
          AND EXISTS (SELECT 1 FROM inserted)
        RETURNING id
    """, car_id, user_id)

    return bool(row)


# ================= CREATE =================

async def create_seller_car(
    seller_id: int,
    model_id: int,
    description: str | None,
    photo_id: str | None,
):
    return await fetchrow(
        """
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
        RETURNING id
        """,
        seller_id,
        model_id,
        photo_id,
        description,
    )


# ================= DELETE =================

async def delete_seller_car(car_id: int, seller_id: int) -> bool:
    row = await fetchrow(
        """
        DELETE FROM seller_cars
        WHERE id = $1
          AND seller_id = $2
        RETURNING id
        """,
        car_id,
        seller_id,
    )
    return row is not None


# ================= UPDATE DESCRIPTION =================

async def update_seller_car_description(car_id: int, seller_id: int, description: str | None) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_cars
        SET description = $1
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        description,
        car_id,
        seller_id,
    )
    return row is not None


# ================= UPDATE PHOTO =================

async def update_seller_car_photo(car_id: int, seller_id: int, photo_id: str) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_cars
        SET photo_id = $1
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        photo_id,
        car_id,
        seller_id,
    )
    return row is not None


# ================= SAFE UNIVERSAL UPDATE =================

async def update_car_field(car_id: int, seller_id: int, field: str, value) -> bool:
    if field == "description":
        return await update_seller_car_description(car_id, seller_id, value)

    if field == "photo_id":
        return await update_seller_car_photo(car_id, seller_id, value)

    return False
