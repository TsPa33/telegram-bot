from fastapi import APIRouter, Request, HTTPException
import base64
import json
import hashlib
import os
import psycopg2

router = APIRouter()

# ================= DB =================

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise Exception("DATABASE_URL not set")

    return psycopg2.connect(database_url)


# ================= SIGNATURE =================

def verify_signature(data: str, signature: str) -> bool:
    private_key = os.getenv("LIQPAY_PRIVATE_KEY")

    if not private_key:
        raise Exception("LIQPAY_PRIVATE_KEY not set")

    sign_string = private_key + data + private_key
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
        amount = payload.get("amount")

        if not order_id:
            raise HTTPException(status_code=400, detail="No order_id")

        # ================= DB UPDATE =================

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE payments
            SET status = %s
            WHERE order_id = %s
            """,
            (status, order_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

        print(f"✅ Payment updated: {order_id} → {status}")

        return {"status": "ok"}

    except Exception as e:
        print("❌ ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
