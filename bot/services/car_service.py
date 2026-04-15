from bot.database.base import fetchrow, fetchval


async def get_cars_page(model_id: int, page: int):
    # 🔢 загальна кількість
    total = await fetchval("""
        SELECT COUNT(*)
        FROM seller_cars
        WHERE model = $1
    """, model_id)

    if not total:
        return None, 0

    # 🧠 гарантія коректного page
    if page < 0:
        page = 0
    if page >= total:
        page = total - 1

    # 🔥 КРИТИЧНО: OFFSET
    car = await fetchrow("""
        SELECT *
        FROM seller_cars
        WHERE model = $1
        ORDER BY id DESC
        LIMIT 1 OFFSET $2
    """, model_id, page)

    return car, total
