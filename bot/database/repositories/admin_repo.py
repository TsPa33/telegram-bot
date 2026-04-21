from bot.database.base import fetch, execute, fetchrow
from bot.database.repositories.request_repo import (
    get_pending_brand_requests,
    get_pending_model_requests,
    approve_brand,
    reject_brand,
    approve_model,
    reject_model,
)


# ================= BRAND =================

async def update_brand_request(request_id: int, new_brand: str):
    await execute("""
        UPDATE brand_requests
        SET brand = $1
        WHERE id = $2
    """, new_brand, request_id)


# ================= MODEL =================

async def update_model_request(request_id: int, new_model: str):
    await execute("""
        UPDATE model_requests
        SET model = $1
        WHERE id = $2
    """, new_model, request_id)


# ================= VERIFICATION =================

async def create_verification_request(seller_id: int, photo_id: str):
    row = await fetchrow("""
        INSERT INTO verification_requests (seller_id, passport_photo_id)
        VALUES ($1, $2)
        ON CONFLICT (seller_id)
        DO UPDATE SET
            passport_photo_id = EXCLUDED.passport_photo_id,
            status = 'pending'
        RETURNING id
    """, seller_id, photo_id)

    return row["id"]


async def get_verification_requests():
    return await fetch("""
        SELECT vr.id, vr.seller_id, vr.passport_photo_id
        FROM verification_requests vr
        WHERE vr.status = 'pending'
        ORDER BY vr.id
    """)


async def approve_seller(request_id: int):
    row = await fetchrow("""
        SELECT s.telegram_id
        FROM verification_requests vr
        JOIN sellers s ON vr.seller_id = s.id
        WHERE vr.id = $1
    """, request_id)

    if not row:
        return None

    telegram_id = row["telegram_id"]

    await execute("""
        UPDATE sellers
        SET is_verified = TRUE
        WHERE telegram_id = $1
    """, telegram_id)

    await execute("""
        UPDATE verification_requests
        SET status = 'approved'
        WHERE id = $1
    """, request_id)

    return telegram_id


async def reject_seller(request_id: int):
    row = await fetchrow("""
        SELECT s.telegram_id
        FROM verification_requests vr
        JOIN sellers s ON vr.seller_id = s.id
        WHERE vr.id = $1
    """, request_id)

    if not row:
        return None

    telegram_id = row["telegram_id"]

    await execute("""
        UPDATE verification_requests
        SET status = 'rejected'
        WHERE id = $1
    """, request_id)

    return telegram_id
