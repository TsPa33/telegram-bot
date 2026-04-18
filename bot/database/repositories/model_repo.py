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


async def get_brands_with_ids() -> list[dict]:
    rows = await fetch("""
        SELECT id, name
        FROM brands
        ORDER BY name
    """)
    return [dict(r) for r in rows]


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


async def get_models_by_brand_id(brand_id: int) -> list[dict]:
    if not brand_id:
        return []

    rows = await fetch("""
        SELECT id, name
        FROM models
        WHERE brand_id = $1
        ORDER BY name
    """, brand_id)
    return [dict(r) for r in rows]


# ================= MODEL ID =================

async def get_model_id(brand: str, model: str) -> int | None:
    """
    Повертає model_id по brand + model.
    Якщо бренду/моделі немає — створює їх.
    """
    if not brand or not model:
        return None

    brand_name = brand.strip()
    model_name = model.strip()

    row = await fetchrow("""
        SELECT m.id
        FROM models m
        JOIN brands b ON m.brand_id = b.id
        WHERE LOWER(b.name) = LOWER($1)
          AND LOWER(m.name) = LOWER($2)
        LIMIT 1
    """, brand_name, model_name)

    if row:
        return row["id"]

    brand_row = await fetchrow("""
        INSERT INTO brands (name)
        VALUES ($1)
        ON CONFLICT (name)
        DO UPDATE SET name = EXCLUDED.name
        RETURNING id
    """, brand_name)

    if not brand_row:
        return None

    model_row = await fetchrow("""
        INSERT INTO models (name, brand_id)
        VALUES ($1, $2)
        RETURNING id
    """, model_name, brand_row["id"])

    return model_row["id"] if model_row else None


# ================= EXISTS =================

async def model_exists(brand: str, model: str) -> bool:
    """
    Перевіряє існування моделі
    """
    return (await get_model_id(brand, model)) is not None
