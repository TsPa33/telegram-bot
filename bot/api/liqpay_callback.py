from fastapi import APIRouter, Request, HTTPException
import base64
import json
import asyncpg
import os
import hashlib

from bot.config import LIQPAY_PRIVATE_KEY

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")


def verify_signature(data: str, signature: str | None) -> bool:
    if not signature or not LIQPAY_PRIVATE_KEY:
        return False

    sign_string = LIQPAY_PRIVATE_KEY + data + LIQPAY_PRIVATE_KEY
    expected_signature = base64.b64encode(
        hashlib.sha1(sign_string.encode()).digest()
    ).decode()

    return signature == expected_signature


@router.post("/liqpay/callback")
async def liqpay_callback(request: Request):
    try:
        form = await request.form()

        data = form.get("data")
        signature = form.get("signature")

        if not data:
            raise HTTPException(status_code=400, detail="No data")

        if not verify_signature(data, signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

        decoded = base64.b64decode(data).decode()
        payload = json.loads(decoded)

        order_id = payload.get("order_id")
        status = payload.get("status")

        if not order_id:
            raise HTTPException(status_code=400, detail="No order_id")

        conn = await asyncpg.connect(DATABASE_URL)

        # 🔹 отримуємо платіж
        payment = await conn.fetchrow(
            """
            SELECT id, seller_id, amount, status
            FROM payments
            WHERE order_id = $1
            """,
            order_id
        )

        # 🔹 оновлюємо статус
        await conn.execute(
            """
            UPDATE payments
            SET status = $1
            WHERE order_id = $2
            """,
            status,
            order_id
        )

        # 🔹 мапінг пакетів
        slots_map = {
            99: 1,
            199: 5,
            299: 10,
        }

        # 🔥 ДОДАЄМО ПІДПИСКУ (ЗАХИСТ ВІД ДУБЛІВ)
        if (
            status == "success"
            and payment
            and payment["status"] != "success"  # ← важливо
            and payment["amount"] in slots_map
        ):
            await conn.execute(
                """
                INSERT INTO seller_subscriptions (seller_id, slots, expires_at, payment_id)
                SELECT $1, $2, NOW() + INTERVAL '30 days', $3
                WHERE NOT EXISTS (
                    SELECT 1 FROM seller_subscriptions WHERE payment_id = $3
                )
                """,
                payment["seller_id"],
                slots_map[payment["amount"]],
                payment["id"]
            )

        await conn.close()

        print(f"✅ PAYMENT UPDATED: {order_id} -> {status}")

        return {"ok": True}

    except Exception as e:
        print(f"❌ CALLBACK ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))