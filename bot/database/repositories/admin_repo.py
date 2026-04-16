from bot.database.base import fetch, fetchrow, execute


# ================= BRAND =================

async def get_pending_brand_requests():
    return await fetch("""
        SELECT id, user_id, brand
        FROM brand_requests
        WHERE status = 'pending'
        ORDER BY id
    """)


async def approve_brand(request_id: int):
    await execute("""
        UPDATE brand_requests
        SET status = 'approved'
        WHERE id = $1
    """, request_id)


async def reject_brand(request_id: int):
    await execute("""
        UPDATE brand_requests
        SET status = 'rejected'
        WHERE id = $1
    """, request_id)


async def update_brand_request(request_id: int, new_brand: str):
    await execute("""
        UPDATE brand_requests
        SET brand = $1
        WHERE id = $2
    """, new_brand, request_id)


# ================= MODEL =================

async def get_pending_model_requests():
    return await fetch("""
        SELECT id, user_id, brand, model
        FROM model_requests
        WHERE status = 'pending'
        ORDER BY id
    """)


async def approve_model(request_id: int):
    row = await fetchrow("""
        SELECT user_id, brand, model
        FROM model_requests
        WHERE id = $1
    """, request_id)

    if not row:
        return None

    await execute("""
        INSERT INTO models (user_id, brand, model)
        VALUES ($1, $2, $3)
        ON CONFLICT (brand, model) DO NOTHING
    """, row["user_id"], row["brand"], row["model"])

    await execute("""
        UPDATE model_requests
        SET status = 'approved'
        WHERE id = $1
    """, request_id)

    return row


async def reject_model(request_id: int):
    await execute("""
        UPDATE model_requests
        SET status = 'rejected'
        WHERE id = $1
    """, request_id)


async def update_model_request(request_id: int, new_model: str):
    await execute("""
        UPDATE model_requests
        SET model = $1
        WHERE id = $2
    """,
