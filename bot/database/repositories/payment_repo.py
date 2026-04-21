from bot.database.base import fetchrow, execute


async def create_payment(seller_id: int, order_id: str, amount: int):
    await execute("""
        INSERT INTO payments (seller_id, order_id, amount, status)
        VALUES ($1, $2, $3, 'pending')
    """, seller_id, order_id, amount)


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
