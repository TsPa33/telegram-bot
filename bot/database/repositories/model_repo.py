from bot.database.base import fetch, fetchrow


# ================= BRANDS =================

async def get_brands() -> list[str]:
    """
    Повертає список назв брендів
    """
    rows = await fetch("""
        SELECT name
        FROM brands
        ORDER BY name
    """)
    return [r["name"] for r in rows]


# ================= MODELS =================

async def get_models_by_brand(brand: str) -> list[str]:
    """
    Повертає список моделей по бренду
    """
    if not brand:
        return []

    rows = await fetch("""
        SELECT m.name
        FROM models m
        JOIN brands b ON m.brand_id = b.id
        WHERE LOWER(b.name) = LOWER($1)
        ORDER BY m.name
    """, brand.strip())

    return [r["name"] for r in rows]


# ================= MODEL ID =================

async def get_model_id(brand: str, model: str) -> int | None:
    """
    Повертає model_id по brand + model
    """
    if not brand or not model:
        return None

    row = await fetchrow("""
        SELECT m.id
        FROM models m
        JOIN brands b ON m.brand_id = b.id
        WHERE LOWER(b.name) = LOWER($1)
          AND LOWER(m.name) = LOWER($2)
        LIMIT 1
    """, brand.strip(), model.strip())

    return row["id"] if row else None


# ================= EXISTS =================

async def model_exists(brand: str, model: str) -> bool:
    """
    Перевіряє існування моделі
    """
    return (await get_model_id(brand, model)) is not None
