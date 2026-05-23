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
          AND status::text IN ('active', '1', 'true', 'enabled', 'published')
    """, model_id)

    return row["total"] if row else 0


# ================= GET FIRST =================

async def get_first_car(model_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status::text IN ('active', '1', 'true', 'enabled', 'published')
        ORDER BY sc.id DESC
        LIMIT 1
    """, model_id)


# ================= GET NEXT =================

async def get_next_car(model_id: int, last_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status::text IN ('active', '1', 'true', 'enabled', 'published')
          AND sc.id < $2
        ORDER BY sc.id DESC
        LIMIT 1
    """, model_id, last_id)


# ================= GET PREV =================

async def get_prev_car(model_id: int, current_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status::text IN ('active', '1', 'true', 'enabled', 'published')
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
          AND sc.status::text IN ('active', '1', 'true', 'enabled', 'published')
        ORDER BY sc.id DESC
    """, seller_id)


# ================= PAGINATION =================

async def get_cars_page(model_id: int, limit: int, offset: int):
    return await fetch(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status::text IN ('active', '1', 'true', 'enabled', 'published')
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

async def archive_seller_car(seller_id: int, car_id: int) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_cars
        SET status = 'deleted'
        WHERE id = $1
          AND seller_id = $2
          AND COALESCE(status, 'active') <> 'deleted'
        RETURNING id
        """,
        car_id,
        seller_id,
    )
    return row is not None


async def delete_seller_car(car_id: int, seller_id: int) -> bool:
    return await archive_seller_car(seller_id=seller_id, car_id=car_id)


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


async def search_cars_for_buyer(query: str, limit: int = 100) -> list:
    pattern = f"%{(query or '').strip()}%"
    return await fetch(
        """
        SELECT
            s.id AS seller_id,
            s.shop_name,
            s.name,
            s.phone,
            s.username,
            s.city,
            s.website,
            ss.subdomain AS site_subdomain,
            s.photo_id AS seller_photo_id,
            s.is_verified,
            NULL::BIGINT AS part_id,
            NULL::TEXT AS part_name,
            NULL::TEXT AS part_category,
            NULL::NUMERIC AS part_price,
            NULL::TEXT AS part_photo_id,
            NULL::TEXT AS part_description,
            sc.id AS car_id,
            b.name AS brand,
            m.name AS model,
            sc.photo_id AS car_photo_id,
            sc.description AS car_description
        FROM seller_cars sc
        JOIN sellers s ON s.id = sc.seller_id
        LEFT JOIN seller_sites ss ON ss.seller_id = s.id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.status::text IN ('active', '1', 'true', 'enabled', 'published')
          AND (
                LOWER(COALESCE(b.name, '')) LIKE LOWER($1)
             OR LOWER(COALESCE(m.name, '')) LIKE LOWER($1)
             OR LOWER(COALESCE(sc.description, '')) LIKE LOWER($1)
          )
        ORDER BY sc.created_at DESC NULLS LAST, sc.id DESC
        LIMIT $2
        """,
        pattern,
        limit,
    )
