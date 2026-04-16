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
        ON CONFLICT DO NOTHING
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
    """, new_model, request_id)


# ================= VERIFICATION =================

async def create_verification_request(seller_id: int, photo_id: str):
    # один активний запит на продавця
    await execute("""
        INSERT INTO verification_requests (seller_id, passport_photo_id)
        VALUES ($1, $2)
        ON CONFLICT (seller_id)
        DO UPDATE SET
            passport_photo_id = EXCLUDED.passport_photo_id,
            status = 'pending'
    """, seller_id, photo_id)


async def get_verification_requests():
    return await fetch("""
        SELECT vr.id, vr.seller_id, vr.passport_photo_id
        FROM verification_requests vr
        JOIN sellers s ON vr.seller_id = s.id
        WHERE vr.status = 'pending'
        ORDER BY vr.id
    """)


async def approve_seller(request_id: int):
    row = await fetchrow("""
        SELECT seller_id
        FROM verification_requests
        WHERE id = $1
    """, request_id)

    if not row:
        return

    seller_id = row["seller_id"]

    await execute("""
        UPDATE sellers
        SET is_verified = TRUE
        WHERE id = $1
    """, seller_id)

    await execute("""
        UPDATE verification_requests
        SET status = 'approved'
        WHERE id = $1
    """, request_id)


async def reject_seller(request_id: int):
    await execute("""
        UPDATE verification_requests
        SET status = 'rejected'
        WHERE id = $1
    """, request_id)
