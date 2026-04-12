from bot.database.base import fetch, fetchrow


DEFAULT_LIMIT = 1


# ================= BASE QUERY =================

BASE_SELECT = """
    SELECT 
        sc.id,
        b.name AS brand,
        m.model,
        sc.photo_id,
        sc.description,
        s.username
    FROM seller_cars sc
    JOIN sellers s ON sc.seller_id = s.id
    JOIN models m ON sc.model_id = m.id
    JOIN brands b ON m.brand_id = b.id
"""


# ================= FIND CARS =================

async def find_cars(
    brand: str,
    model: str,
    page: int = 0,
    limit: int = DEFAULT_LIMIT
):
    offset = page * limit

    return await fetch(f"""
        {BASE_SELECT}
        WHERE b.name = $1
          AND m.model = $2
          AND sc.status = 'active'
        ORDER BY sc.id DESC
        LIMIT $3 OFFSET $4
    """, brand, model, limit, offset)


# ================= COUNT =================

async def count_cars(brand: str, model: str) -> int:
    row = await fetchrow("""
        SELECT COUNT(*) as total
        FROM seller_cars sc
        JOIN models m ON sc.model_id = m.id
        JOIN brands b ON m.brand_id = b.id
        WHERE b.name = $1
          AND m.model = $2
          AND sc.status = 'active'
    """, brand, model)

    return row["total"] if row else 0


# ================= SELLER CARS =================

async def get_seller_cars(telegram_id: int):
    return await fetch(f"""
        {BASE_SELECT}
        WHERE s.telegram_id = $1
        ORDER BY sc.id DESC
    """, telegram_id)


# ================= GET ONE CAR =================

async def get_car_by_id(car_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.id = $1
    """, car_id)
