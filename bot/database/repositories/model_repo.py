from bot.database.base import fetch, fetchrow


# ================= BRANDS =================

async def get_brands():
    rows = await fetch("""
        SELECT name
        FROM brands
        ORDER BY name
    """)
    return [r["name"] for r in rows]


# ================= MODELS =================

async def get_models_by_brand(brand: str):
    rows = await fetch("""
        SELECT m.name
        FROM models m
        JOIN brands b ON m.brand_id = b.id
        WHERE LOWER(b.name) = LOWER($1)
        ORDER BY m.name
    """, brand)

    return [r["name"] for r in rows]


# ================= MODEL ID =================

async def get_model_id(brand: str, model: str):
    row = await fetchrow("""
        SELECT m.id
        FROM models m
        JOIN brands b ON m.brand_id = b.id
        WHERE LOWER(b.name) = LOWER($1)
          AND LOWER(m.name) = LOWER($2)
    """, brand, model)

    return row["id"] if row else None


# ================= EXISTS =================

async def model_exists(brand: str, model: str):
    return (await get_model_id(brand, model)) is not None
