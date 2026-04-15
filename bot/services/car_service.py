from bot.database.base import fetchrow


async def get_cars_page(model_id: int, page: int):
    # 🔢 total через fetchrow
    total_row = await fetchrow("""
        SELECT COUNT(*) as total
        FROM seller_cars
        WHERE model = $1
    """, model_id)

    total = total_row["total"] if total_row else 0

    if total == 0:
        return None, 0

    # 🧠 захист
    if page < 0:
        page = 0
    if page >= total:
        page = total - 1

    # 🔥 OFFSET — ключ pagination
    car = await fetchrow("""
        SELECT *
        FROM seller_cars
        WHERE model = $1
        ORDER BY id DESC
        LIMIT 1 OFFSET $2
    """, model_id, page)

    return car, total
