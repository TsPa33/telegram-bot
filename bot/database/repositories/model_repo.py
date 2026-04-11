from bot.database.base import fetch, fetchrow


async def get_brands():
    rows = await fetch("""
        SELECT DISTINCT brand FROM models ORDER BY brand
    """)
    return [r["brand"] for r in rows]


async def get_models_by_brand(brand: str):
    rows = await fetch("""
        SELECT model FROM models
        WHERE LOWER(brand) = LOWER($1)
        ORDER BY model
    """, brand)

    return [r["model"] for r in rows]


async def get_model_id(brand: str, model: str):
    row = await fetchrow("""
        SELECT id FROM models
        WHERE LOWER(brand)=LOWER($1)
        AND LOWER(model)=LOWER($2)
    """, brand, model)

    return row["id"] if row else None


async def model_exists(brand: str, model: str):
    return await get_model_id(brand, model) is not None
