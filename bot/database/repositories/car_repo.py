from bot.database.base import fetch, fetchrow


DEFAULT_LIMIT = 5


# ================= BASE QUERY =================

BASE_SELECT = """
    SELECT 
        sc.id,
        b.name AS brand,
        m.model,
        sc.photo_id,
        sc.description,
        sc.is_catalog,

        -- seller
        s.username,
        s.telegram_id,
        s.name,
        s.shop_name,
        s.phone,
        s.website,
        s.city

    FROM seller_cars sc
    JOIN sellers s ON sc.seller_id = s.id
    JOIN models m ON sc.model_id = m.id
    JOIN brands b ON m.brand_id = b.id
"""


# ================= FIND CARS =================

async def find_cars(model_id: int, page: int = 0, limit: int = 1):
    offset = page * limit

    return await fetch("""
        SELECT 
            sc.id,
            sc.photo_id,
            sc.description,
            sc.is_catalog,

            m.model,
            b.name AS brand,

            s.username,
            s.telegram_id,
            s.name,
            s.shop_name,
            s.phone,
            s.website,
            s.city

        FROM seller_cars sc
        JOIN models m ON sc.model_id = m.id
        JOIN brands b ON m.brand_id = b.id
        JOIN sellers s ON sc.seller_id = s.id

        WHERE sc.model_id = $1
          AND sc.status = 'active'

        ORDER BY sc.is_catalog ASC, sc.id DESC
        LIMIT $2 OFFSET $3
    """, model_id, limit, offset)


# ================= COUNT =================

async def count_cars(model_id: int) -> int:
    row = await fetchrow("""
        SELECT COUNT(*) as total
        FROM seller_cars
        WHERE model_id = $1
          AND status = 'active'
    """, model_id)

    return row["total"] if row else 0


# ================= SELLER CARS =================

async def get_seller_cars(telegram_id: int):
    return await fetch(f"""
        {BASE_SELECT}
        WHERE s.telegram_id = $1
        ORDER BY sc.id DESC
        LIMIT 20
    """, telegram_id)


# ================= GET ONE CAR =================

async def get_car_by_id(car_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.id = $1
    """, car_id)
