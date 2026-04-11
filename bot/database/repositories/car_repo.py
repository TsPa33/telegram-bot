from bot.database.base import fetch, fetchrow


DEFAULT_LIMIT = 1  # для swipe UX


# ================= FIND CARS =================

async def find_cars(
    brand: str,
    model: str,
    page: int = 0,
    limit: int = DEFAULT_LIMIT
):
    offset = page * limit

    return await fetch("""
        SELECT 
            s.username,
            m.brand,
            m.model,
            sc.photo_id,
            sc.description
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        WHERE m.brand = $1
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
        WHERE m.brand = $1
          AND m.model = $2
          AND sc.status = 'active'
    """, brand, model)

    return row["total"] if row else 0
