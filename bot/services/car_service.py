from bot.database.base import fetchrow


# ================= MODEL =================

from bot.database.repositories.model_repo import (
    get_brand_by_name,
    get_model_by_name_and_brand
)


async def get_model_or_none(brand: str, model: str):
    # 1. отримуємо brand_id
    brand_obj = await get_brand_by_name(brand)

    if not brand_obj:
        return None

    brand_id = brand_obj["id"]

    # 2. отримуємо model
    model_obj = await get_model_by_name_and_brand(model, brand_id)

    if not model_obj:
        return None

    return model_obj["id"]


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
