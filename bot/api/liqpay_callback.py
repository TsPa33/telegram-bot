from fastapi import APIRouter, Request, HTTPException
import base64
import json
import hashlib
import logging
from datetime import datetime
import pytz

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import LIQPAY_PRIVATE_KEY, BOT_TOKEN
from bot.database.base import execute, fetchrow
from bot.services.domain_service import build_site_url
from bot.config import SELLER_CRM_BASE_URL
from bot.services.seller_crm import SELLER_CRM_PRODUCT, SELLER_CRM_SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)

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
        logger.info("LIQPAY_CALLBACK_HIT")

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
            SELECT id, seller_id, amount, status, COALESCE(product_type, product) AS product
            FROM payments
            WHERE order_id = $1
            """,
            order_id
        )

        if not payment:
            logger.warning("LIQPAY_CALLBACK_PAYMENT_NOT_FOUND order_id=%s", order_id)
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

        product = payment.get("product") or "garage"

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
        if product in {"site", "site_standard", "site_plus"} and status == "success":

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

        # ===== ПРОФЕСІЙНА CRM =====
        if product == SELLER_CRM_PRODUCT and status == "success":
            from bot.database.repositories.seller_crm_repo import create_crm_subscription

            await create_crm_subscription(
                payment["seller_id"],
                payment["id"],
                days=SELLER_CRM_SUBSCRIPTION_DAYS,
            )

        # ===== NOTIFICATIONS =====

        seller_data = await fetchrow(
            "SELECT telegram_id FROM sellers WHERE id = $1",
            payment["seller_id"]
        )

        if seller_data:
            telegram_id = seller_data["telegram_id"]
            kyiv_tz = pytz.timezone("Europe/Kyiv")
            now = datetime.now(kyiv_tz).strftime("%d.%m.%Y %H:%M")

            reply_markup = None
            if status == "success":
                if product == "garage":
                    crm_account = await fetchrow(
                        "SELECT crm_slug FROM seller_crm_accounts WHERE seller_id = $1 AND is_active = TRUE LIMIT 1",
                        payment["seller_id"],
                    )
                    add_car_url = None
                    if crm_account and crm_account.get("crm_slug"):
                        crm_base_url = (SELLER_CRM_BASE_URL or "https://crm.carpot.com.ua").rstrip("/")
                        add_car_url = f"{crm_base_url}/crm/seller/{crm_account['crm_slug']}/content/cars/create"
                    text = (
                        "✅ Пакет активовано.\n\n"
                        f"Доступно авто на розборі: {slots_map.get(amount, 0)}\n\n"
                        "Тепер додайте авто на розбір — CarPot створить запчастини та почне приймати заявки.\n"
                    )
                    if add_car_url:
                        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="➕ Додати авто", url=add_car_url)
                        ]])
                elif product == SELLER_CRM_PRODUCT:
                    crm_base_url = (SELLER_CRM_BASE_URL or "https://crm.carpot.com.ua").rstrip("/")
                    text = (
                        "💼 Професійна CRM активована на 30 днів\n\n"
                        "Натисніть у боті «💼 Професійна CRM» → «Створити CRM акаунт», "
                        "щоб обрати адресу та пароль.\n\n"
                        f"Демо: {crm_base_url}/crm/seller/demo\n"
                    )
                elif product in {"site", "site_standard", "site_plus"}:
                    package_titles = {
                        "site_standard": "Сайт для авторозборки — 499 грн / рік",
                        "site_plus": "Сайт-візитка для послуг — 1499 грн",
                        "site": "Сайт для авторозборки — 499 грн / рік",
                    }
                    text = (
                        f"🌐 Оплата підтверджена: {package_titles.get(product, 'Пакет сайту')}\n\n"
                        f"Сайт створено автоматично\n\n"
                        f"🔗 {build_site_url(subdomain)}\n\n"
                        f"Редагування: «Мій сайт» у боті\n"
                    )

                text += now
                await bot.send_message(telegram_id, text, reply_markup=reply_markup)

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
        logger.exception("LIQPAY_CALLBACK_ERROR")
        raise HTTPException(status_code=500, detail=str(e))
