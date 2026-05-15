import logging

from bot.database.base import fetchrow, fetch, execute

logger = logging.getLogger(__name__)


async def ensure_payment_product_type_column():
    await execute(
        """
        ALTER TABLE payments
        ADD COLUMN IF NOT EXISTS product_type TEXT NOT NULL DEFAULT 'garage'
        """
    )
    await execute(
        """
        UPDATE payments
        SET product_type = product
        WHERE product IS NOT NULL
          AND product_type = 'garage'
          AND product <> 'garage'
        """
    )


async def create_payment(
    seller_id: int,
    order_id: str,
    amount: int,
    product: str = "garage",
):
    await ensure_payment_product_type_column()

    try:
        payment = await fetchrow(
            """
            INSERT INTO payments (seller_id, order_id, amount, status, product, product_type)
            VALUES ($1, $2, $3, 'pending', $4, $4)
            RETURNING id, seller_id, order_id, amount, status, product, product_type, created_at
            """,
            seller_id,
            order_id,
            amount,
            product,
        )
    except Exception:
        logger.exception(
            "PAYMENT_ROW_CREATE_FAILED seller_id=%s order_id=%s amount=%s product_type=%s",
            seller_id,
            order_id,
            amount,
            product,
        )
        raise

    if not payment:
        logger.error(
            "PAYMENT_ROW_CREATE_EMPTY_RESULT seller_id=%s order_id=%s amount=%s product_type=%s",
            seller_id,
            order_id,
            amount,
            product,
        )
        raise RuntimeError("Payment row was not created")

    logger.info(
        "PAYMENT_ROW_CREATED id=%s seller_id=%s order_id=%s amount=%s status=%s product_type=%s",
        payment["id"],
        payment["seller_id"],
        payment["order_id"],
        payment["amount"],
        payment["status"],
        payment["product_type"],
    )
    return payment


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
    await ensure_payment_product_type_column()
    return await fetch("""
        SELECT 
            p.amount,
            p.status,
            COALESCE(p.product_type, p.product) AS product,
            p.created_at,
            ss.slots
        FROM payments p
        JOIN sellers s ON s.id = p.seller_id
        LEFT JOIN seller_subscriptions ss ON ss.payment_id = p.id
        WHERE s.telegram_id = $1
        ORDER BY p.created_at DESC
        LIMIT 20
    """, telegram_id)
