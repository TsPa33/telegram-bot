from fastapi import APIRouter, Request, HTTPException
import base64
import json
import asyncpg
import os

router = APIRouter()

DATABASE_URL = os.getenv("DATABASE_URL")


@router.post("/liqpay/callback")
async def liqpay_callback(request: Request):
    try:
        form = await request.form()

        data = form.get("data")
        signature = form.get("signature")

        if not data:
            raise HTTPException(status_code=400, detail="No data")

        # ❗ TEMP: без перевірки підпису
        # (потім повернемо назад)

        # decode base64
        decoded = base64.b64decode(data).decode()
        payload = json.loads(decoded)

        order_id = payload.get("order_id")
        status = payload.get("status")

        if not order_id:
            raise HTTPException(status_code=400, detail="No order_id")

        conn = await asyncpg.connect(DATABASE_URL)

        await conn.execute(
            """
            UPDATE payments
            SET status = $1
            WHERE order_id = $2
            """,
            status,
            order_id
        )

        await conn.close()

        print(f"✅ PAYMENT UPDATED: {order_id} -> {status}")

        return {"ok": True}

    except Exception as e:
        print(f"❌ CALLBACK ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))
