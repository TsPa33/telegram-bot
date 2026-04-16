from bot.database.base import fetchrow


# ================= MODEL =================

async def get_model_or_none(brand: str, model_name: str):
    row = await fetchrow("""
        SELECT m.id
        FROM models m
        JOIN brands b ON m.brand_id = b.id
        WHERE LOWER(b.name) = LOWER($1)
          AND LOWER(m.name) = LOWER($2)
        LIMIT 1
    """, brand, model_name)

    return row["id"] if row else None


# ================= PAGINATION =================

async def get_cars_page(model_id: int, page: int):
    # 🔢 total
    total_row = await fetchrow("""
        SELECT COUNT(*) AS total
        FROM seller_cars
        WHERE model_id = $1
          AND status = 1
    """, model_id)

    total = total_row["total"] if total_row else 0

    if total == 0:
        return None, 0

    # 🧠 захист
    if page < 0:
        page = 0
    if page >= total:
        page = total - 1

    # 🔥 OFFSET (тимчасово залишаємо, далі приберемо)
    car = await fetchrow("""
        SELECT *
        FROM seller_cars
        WHERE model_id = $1
          AND status = 1
        ORDER BY id DESC
        LIMIT 1 OFFSET $2
    """, model_id, page)

    return car, total
