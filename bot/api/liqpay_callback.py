from fastapi import APIRouter, Request, HTTPException
import base64
import json
import hashlib
import os
import psycopg2
from aiogram import Bot

router = APIRouter()

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
LIQPAY_PRIVATE_KEY = os.getenv("LIQPAY_PRIVATE_KEY")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

if not LIQPAY_PRIVATE_KEY:
    raise Exception("LIQPAY_PRIVATE_KEY not set")

bot = Bot(token=BOT_TOKEN)

# ================= DB =================

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise Exception("DATABASE_URL not set")

    return psycopg2.connect(database_url)

# ================= SIGNATURE =================

def verify_signature(data: str, signature: str) -> bool:
    sign_string = LIQPAY_PRIVATE_KEY + data + LIQPAY_PRIVATE_KEY
    expected_signature = base64.b64encode(
        hashlib.sha1(sign_string.encode()).digest()
    ).decode()

    return expected_signature == signature

# ================= CALLBACK =================

@router.post("/liqpay/callback")
async def liqpay_callback(request: Request):
    try:
        body = await request.json()

        data = body.get("data")
        signature = body.get("signature")

        if not data or not signature:
            raise HTTPException(status_code=400, detail="Invalid request")

        # ✅ перевірка підпису
        if not verify_signature(data, signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

        # ✅ декодуємо payload
        decoded_data = base64.b64decode(data).decode()
        payload = json.loads(decoded_data)

        order_id = payload.get("order_id")
        status = payload.get("status")

        if not order_id:
            raise HTTPException(status_code=400, detail="No order_id")

        conn = get_db_connection()
        cursor = conn.cursor()

        # ================= CHECK CURRENT STATUS =================

        cursor.execute(
            "SELECT status, seller_id FROM payments WHERE order_id = %s",
            (order_id,)
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Payment not found")

        current_status, seller_id = row

        # ❗ захист від дублювання
        if current_status == "success":
            return {"status": "already processed"}

        # ================= UPDATE PAYMENT =================

        cursor.execute(
            """
            UPDATE payments
            SET status = %s
            WHERE order_id = %s
            """,
            (status, order_id)
        )

        # ================= SUCCESS LOGIC =================

        if status == "success":
            # ➕ додаємо слот
            cursor.execute(
                """
                UPDATE sellers
                SET cars_limit = cars_limit + 1
                WHERE id = %s
                """,
                (seller_id,)
            )

            # 📩 отримуємо telegram_id
            cursor.execute(
                "SELECT telegram_id FROM sellers WHERE id = %s",
                (seller_id,)
            )
            result = cursor.fetchone()

            if result:
                telegram_id = result[0]

                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text="✅ Оплата успішна!\n\nВам додано +1 слот 🚗"
                    )
                except Exception as e:
                    print("❌ Telegram error:", e)

        conn.commit()
        cursor.close()
        conn.close()

        print(f"✅ Payment processed: {order_id} → {status}")

        return {"status": "ok"}

    except Exception as e:
        print("❌ ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
