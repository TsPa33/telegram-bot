from bot.database.base import fetchrow
from bot.database.repositories.model_repo import get_model_id


# ================= MODEL =================

async def get_model_or_none(brand: str, model: str) -> int | None:
    """
    Повертає model_id через repo (JOIN brands + models)
    """
    return await get_model_id(brand, model)


# ================= PAGINATION =================

async def get_cars_page(model_id: int, page: int):
    """
    Повертає 1 авто + total
    """

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

    # 🧠 захист від кривих значень
    if page < 0:
        page = 0
    if page >= total:
        page = total - 1

    # 🔥 отримати авто
    car = await fetchrow("""
        SELECT *
        FROM seller_cars
        WHERE model_id = $1
          AND status = 1
        ORDER BY id DESC
        LIMIT 1 OFFSET $2
    """, model_id, page)

    return car, total
