from bot.database.base import fetch, fetchrow


# ================= BASE SELECT =================

BASE_SELECT = """
    SELECT 
        sc.id,
        sc.photo_id,
        sc.description,

        m.name AS model,
        b.name AS brand,

        s.username,
        s.telegram_id,
        s.phone

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
          AND status = 1
    """, model_id)

    return row["total"] if row else 0


# ================= GET FIRST CAR =================

async def get_first_car(model_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status = 1
        ORDER BY sc.id DESC
        LIMIT 1
    """, model_id)


# ================= GET NEXT =================

async def get_next_car(model_id: int, last_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status = 1
          AND sc.id < $2
        ORDER BY sc.id DESC
        LIMIT 1
    """, model_id, last_id)


# ================= GET PREV =================

async def get_prev_car(model_id: int, current_id: int):
    return await fetchrow(f"""
        {BASE_SELECT}
        WHERE sc.model_id = $1
          AND sc.status = 1
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
