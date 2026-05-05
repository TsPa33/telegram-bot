from bot.database.base import fetchrow, fetch, execute


async def create_payment(
    seller_id: int,
    order_id: str,
    amount: int,
    product: str = "garage"   # 🔥 NEW
):
    await execute("""
        INSERT INTO payments (seller_id, order_id, amount, status, product)
        VALUES ($1, $2, $3, 'pending', $4)
    """, seller_id, order_id, amount, product)


async def get_payment(order_id: str):
    return await fetchrow("""
        SELECT * FROM payments
        WHERE order_id = $1
    """, order_id)


async def mark_payment_success(order_id: str):
    await execute("""
        UPDATE payments
        SET status = 'success'
        WHERE order_id = $1
    """, order_id)


# ================= 🔥 UPDATED =================

async def get_user_transactions(telegram_id: int):
    return await fetch("""
        SELECT 
            p.amount,
            p.status,
            p.product,
            p.created_at,
            ss.slots
        FROM payments p
        JOIN sellers s ON s.id = p.seller_id
        LEFT JOIN seller_subscriptions ss ON ss.payment_id = p.id
        WHERE s.telegram_id = $1
        ORDER BY p.created_at DESC
        LIMIT 20
    """, telegram_id)
