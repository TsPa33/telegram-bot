from bot.database.base import fetchrow


# ================= MODEL =================

async def get_model_or_none(brand_id: int, model_name: str):
    return await fetchrow("""
        SELECT *
        FROM models
        WHERE brand_id = $1 AND LOWER(model) = LOWER($2)
    """, brand_id, model_name)


# ================= PAGINATION =================

async def get_cars_page(model_id: int, page: int):
    total_row = await fetchrow("""
        SELECT COUNT(*) AS total
        FROM seller_cars
        WHERE model = $1
    """, model_id)

    total = total_row["total"] if total_row else 0

    if total == 0:
        return None, 0

    if page < 0:
        page = 0
    if page >= total:
        page = total - 1

    car = await fetchrow("""
        SELECT *
        FROM seller_cars
        WHERE model = $1
        ORDER BY id DESC
        LIMIT 1 OFFSET $2
    """, model_id, page)

    return car, total
