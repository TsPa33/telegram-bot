from bot.database.base import fetchrow, execute, fetch


async def get_or_create_seller(telegram_id: int, username: str):
    return await fetchrow("""
        INSERT INTO sellers (telegram_id, username)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id)
        DO UPDATE SET username = EXCLUDED.username
        RETURNING id
    """, telegram_id, username)


async def add_seller_car(seller_id: int, model_id: int, photo_id: str, description: str):
    await execute("""
        INSERT INTO seller_cars (seller_id, model_id, photo_id, description)
        VALUES ($1, $2, $3, $4)
    """, seller_id, model_id, photo_id, description)


async def get_seller_cars(telegram_id: int):
    return await fetch("""
        SELECT sc.id, m.brand, m.model, sc.description
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        WHERE s.telegram_id = $1
    """, telegram_id)


async def delete_car(car_id: int):
    await execute("DELETE FROM seller_cars WHERE id = $1", car_id)


async def update_description(car_id: int, description: str):
    await execute("""
        UPDATE seller_cars
        SET description = $1
        WHERE id = $2
    """, description, car_id)
    
    # ================= PROFILE UPDATE =================

ALLOWED_FIELDS = {
    "shop_name",
    "name",
    "phone",
    "website",
    "city",
    "description"
}


async def update_seller_field(seller_id: int, field: str, value: str | None):
    if field not in ALLOWED_FIELDS:
        return

    await execute(f"""
        UPDATE sellers
        SET {field} = $1
        WHERE id = $2
    """, value, seller_id)
