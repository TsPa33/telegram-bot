from bot.database.base import execute, fetch


async def find_cars(brand: str, model: str):
    return await fetch("""
        SELECT 
            s.username,
            m.brand,
            m.model,
            sc.photo_id
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        WHERE LOWER(m.brand) = LOWER($1)
        AND LOWER(m.model) = LOWER($2)
        AND sc.status = 'active'
        LIMIT 10
    """, brand, model)
