from bot.database.base import execute, fetch, fetchrow


# ================= CREATE =================

async def create_brand_request(user_id: int, brand: str) -> bool:
    existing = await fetchrow("""
        SELECT id FROM brands
        WHERE LOWER(name) = LOWER($1)
        LIMIT 1
    """, brand)

    if existing:
        return False

    duplicate = await fetchrow("""
        SELECT id FROM brand_requests
        WHERE user_id = $1
          AND LOWER(brand) = LOWER($2)
          AND status IN ('pending', 'approved')
        LIMIT 1
    """, user_id, brand)

    if duplicate:
        return False

    await execute("""
        INSERT INTO brand_requests (user_id, brand, status)
        VALUES ($1, $2, 'pending')
        ON CONFLICT (user_id, brand) DO NOTHING
    """, user_id, brand)

    return True


async def create_model_request(user_id: int, brand: str, model: str) -> bool:
    existing = await fetchrow("""
        SELECT m.id
        FROM models m
        JOIN brands b ON b.id = m.brand_id
        WHERE LOWER(b.name) = LOWER($1)
          AND LOWER(m.name) = LOWER($2)
        LIMIT 1
    """, brand, model)

    if existing:
        return False

    duplicate = await fetchrow("""
        SELECT id FROM model_requests
        WHERE user_id = $1
          AND LOWER(brand) = LOWER($2)
          AND LOWER(model) = LOWER($3)
          AND status IN ('pending', 'approved')
        LIMIT 1
    """, user_id, brand, model)

    if duplicate:
        return False

    await execute("""
        INSERT INTO model_requests (user_id, brand, model, status)
        VALUES ($1, $2, $3, 'pending')
        ON CONFLICT (user_id, brand, model) DO NOTHING
    """, user_id, brand, model)

    return True


# ================= PENDING =================

async def get_pending_brand_requests():
    return await fetch("""
        SELECT id, user_id, brand
        FROM brand_requests
        WHERE status = 'pending'
        ORDER BY id
    """)


async def get_pending_model_requests():
    return await fetch("""
        SELECT id, user_id, brand, model
        FROM model_requests
        WHERE status = 'pending'
        ORDER BY id
    """)


# ================= APPROVE =================

async def approve_brand(request_id: int):
    row = await fetchrow("""
        SELECT brand
        FROM brand_requests
        WHERE id = $1
    """, request_id)

    if not row:
        return

    brand = row["brand"]

    await execute("""
        INSERT INTO brands (name)
        VALUES ($1)
        ON CONFLICT (name) DO NOTHING
    """, brand)

    await execute("""
        UPDATE brand_requests
        SET status = 'approved'
        WHERE id = $1
    """, request_id)

    print("APPROVED BRAND:", request_id)


async def approve_model(request_id: int):
    row = await fetchrow("""
        SELECT brand, model
        FROM model_requests
        WHERE id = $1
    """, request_id)

    if not row:
        return

    brand = row["brand"]
    model = row["model"]

    brand_row = await fetchrow("""
        SELECT id FROM brands
        WHERE LOWER(name) = LOWER($1)
        LIMIT 1
    """, brand)

    if not brand_row:
        brand_row = await fetchrow("""
            INSERT INTO brands (name)
            VALUES ($1)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """, brand)

    await execute("""
        INSERT INTO models (name, brand_id)
        VALUES ($1, $2)
        ON CONFLICT (brand_id, name) DO NOTHING
    """, model, brand_row["id"])

    await execute("""
        UPDATE model_requests
        SET status = 'approved'
        WHERE id = $1
    """, request_id)

    print("APPROVED MODEL:", request_id)


# ================= REJECT =================

async def reject_brand(request_id: int):
    await execute("""
        UPDATE brand_requests
        SET status = 'rejected'
        WHERE id = $1
    """, request_id)


async def reject_model(request_id: int):
    await execute("""
        UPDATE model_requests
        SET status = 'rejected'
        WHERE id = $1
    """, request_id)