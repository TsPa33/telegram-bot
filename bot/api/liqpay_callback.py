from fastapi import APIRouter, Request, HTTPException
import base64
import json
import hashlib

from bot.config import LIQPAY_PRIVATE_KEY
from bot.database.base import execute, fetchrow

router = APIRouter()


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
        print("🔥 CALLBACK HIT")

        form = await request.form()

        data = form.get("data")
        signature = form.get("signature")

        if not data:
            raise HTTPException(status_code=400, detail="No data")

        if not verify_signature(data, signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

        decoded = base64.b64decode(data).decode()
        payload = json.loads(decoded)

        print("PAYLOAD:", payload)

        order_id = payload.get("order_id")
        raw_status = payload.get("status")

        if not order_id:
            raise HTTPException(status_code=400, detail="No order_id")

        # ✅ нормалізація статусу
        status = "success" if raw_status in ("success", "sandbox") else "failed"

        print("NORMALIZED STATUS:", status)

        # 🔹 отримуємо платіж
        payment = await fetchrow(
            """
            SELECT id, seller_id, amount, status
            FROM payments
            WHERE order_id = $1
            """,
            order_id
        )

        print("DB PAYMENT:", payment)

        if not payment:
            return {"ok": True}

        # 🔒 захист від повторної обробки
        if payment["status"] == "success":
            print("⚠️ PAYMENT ALREADY PROCESSED")
            return {"ok": True}

        # 🔹 оновлюємо статус
        await execute(
            """
            UPDATE payments
            SET status = $1
            WHERE order_id = $2
            """,
            status,
            order_id
        )

        # 🔥 нормалізація amount (float → int)
        try:
            amount = int(float(payment["amount"]))
        except Exception:
            print("❌ INVALID AMOUNT:", payment["amount"])
            return {"ok": True}

        slots_map = {
            99: 1,
            199: 5,
            299: 10,
        }

        print("AMOUNT NORMALIZED:", amount)

        # ================= ОСНОВНА ЛОГІКА =================

        if status == "success" and amount in slots_map:
            print("💰 ADDING SUBSCRIPTION")

            slots = slots_map[amount]

            await execute(
                """
                INSERT INTO seller_subscriptions (seller_id, slots, expires_at, payment_id)
                SELECT $1, $2, NOW() + INTERVAL '30 days', $3
                WHERE NOT EXISTS (
                    SELECT 1 
                    FROM seller_subscriptions 
                    WHERE payment_id = $3
                )
                """,
                payment["seller_id"],
                slots,
                payment["id"]
            )

            print(f"✅ SUBSCRIPTION ADDED: seller_id={payment['seller_id']}, slots={slots}")

            # ================= TELEGRAM NOTIFY =================

            # 🔥 FIX: локальний імпорт (без circular import)
            from bot.main import bot

            seller = await fetchrow(
                "SELECT telegram_id FROM sellers WHERE id = $1",
                payment["seller_id"]
            )

            if seller:
                telegram_id = seller["telegram_id"]

                try:
                    await bot.send_message(
                        telegram_id,
                        f"✅ Оплата успішна!\n\n"
                        f"🎉 Вам нараховано {slots} слот(ів)\n"
                        f"📅 Дійсно 30 днів"
                    )
                except Exception as e:
                    print("❌ TELEGRAM SEND ERROR:", e)

        else:
            print("⚠️ SKIPPED SUBSCRIPTION:", status, amount)

        print(f"✅ PAYMENT UPDATED: {order_id} -> {status}")

        return {"ok": True}

    except Exception as e:
        print(f"❌ CALLBACK ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))
