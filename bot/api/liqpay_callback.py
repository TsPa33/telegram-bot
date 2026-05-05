from fastapi import APIRouter, Request, HTTPException
import base64
import json
import hashlib
from datetime import datetime
import pytz

from aiogram import Bot

from bot.config import LIQPAY_PRIVATE_KEY, BOT_TOKEN
from bot.database.base import execute, fetchrow

router = APIRouter()

bot = Bot(token=BOT_TOKEN)


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

        order_id = payload.get("order_id")
        raw_status = payload.get("status")

        if not order_id:
            raise HTTPException(status_code=400, detail="No order_id")

        status = "success" if raw_status in ("success", "sandbox") else "failed"

        payment = await fetchrow(
            """
            SELECT id, seller_id, amount, status, product
            FROM payments
            WHERE order_id = $1
            """,
            order_id
        )

        if not payment:
            return {"ok": True}

        await execute(
            """
            UPDATE payments
            SET status = $1
            WHERE order_id = $2
            """,
            status,
            order_id
        )

        try:
            amount = int(float(payment["amount"]))
        except Exception:
            return {"ok": True}

        product = payment.get("product", "garage")

        slots_map = {
            99: 1,
            199: 5,
            299: 10,
        }

        # ===== ГАРАЖ =====
        if product == "garage" and status == "success" and amount in slots_map:
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
                slots_map[amount],
                payment["id"]
            )

        # ===== САЙТ =====
        if product == "site" and status == "success":

            # 1. активуємо доступ
            await execute(
                """
                UPDATE sellers
                SET has_site = TRUE
                WHERE id = $1
                """,
                payment["seller_id"]
            )

            # 2. перевіряємо чи вже є сайт
            site = await fetchrow(
                """
                SELECT * FROM seller_sites
                WHERE seller_id = $1
                """,
                payment["seller_id"]
            )

            # 3. створюємо якщо нема
            if not site:
                from bot.database.repositories.site_repo import create_site
                from bot.services.site_config import get_default_site_config

                subdomain = f"user{payment['seller_id']}"

                await create_site(
                    seller_id=payment["seller_id"],
                    subdomain=subdomain,
                    config=get_default_site_config()
                )
            else:
                subdomain = site["subdomain"]

        # ===== NOTIFICATIONS =====

        seller_data = await fetchrow(
            "SELECT telegram_id FROM sellers WHERE id = $1",
            payment["seller_id"]
        )

        if seller_data:
            telegram_id = seller_data["telegram_id"]
            kyiv_tz = pytz.timezone("Europe/Kyiv")
            now = datetime.now(kyiv_tz).strftime("%d.%m.%Y %H:%M")

            if status == "success":
                if product == "garage":
                    text = (
                        f"✅ Оплата {amount} грн\n"
                        f"Зараховано {slots_map.get(amount, 0)} місце(ць)\n"
                    )
                else:
                    text = (
                        f"🌐 Сайт створено автоматично\n\n"
                        f"🔗 https://worker-production-e30f.up.railway.app/site/{subdomain}\n\n"
                        f"Редагування: «Мій сайт» у боті\n"
                    )

                text += now
                await bot.send_message(telegram_id, text)

            else:
                reason = payload.get("err_description")

                text = (
                    f"⚠️ Оплата {amount} грн\n"
                    f"(В оплаті відмовлено)\n"
                )

                if reason:
                    text += f"Причина: {reason}\n"

                text += now

                await bot.send_message(telegram_id, text)

        return {"ok": True}

    except Exception as e:
        print(f"❌ CALLBACK ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))
