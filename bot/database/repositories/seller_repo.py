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
    rows = await fetch("""
        SELECT m.brand, m.model, sc.description
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        WHERE s.telegram_id = $1
    """, telegram_id)

    return [(r["brand"], r["model"], r["description"]) for r in rows]
