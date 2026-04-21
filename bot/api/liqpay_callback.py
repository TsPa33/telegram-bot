import base64
import json
import hashlib
import logging

from fastapi import APIRouter, Request, HTTPException

from bot.database.repositories.payment_repo import get_payment, mark_payment_success
from bot.database.repositories.seller_repo import add_slot
from bot.config import LIQPAY_PRIVATE_KEY

router = APIRouter()

logger = logging.getLogger(__name__)


def verify_signature(data: str, signature: str) -> bool:
    sign_string = LIQPAY_PRIVATE_KEY + data + LIQPAY_PRIVATE_KEY
    expected = base64.b64encode(
        hashlib.sha1(sign_string.encode()).digest()
    ).decode()
    return expected == signature


@router.post("/liqpay/callback")
async def liqpay_callback(request: Request):
    try:
        form = await request.form()

        data = form.get("data")
        signature = form.get("signature")

        if not data or not signature:
            raise HTTPException(status_code=400, detail="Invalid request")

        # 🔐 перевірка підпису
        if not verify_signature(data, signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

        # 📦 декодування payload
        decoded = json.loads(base64.b64decode(data).decode())
        logger.info(f"LiqPay callback: {decoded}")

        # ❗ обробляємо тільки успішні платежі
        if decoded.get("status") != "success":
            return {"status": "ignored"}

        order_id = decoded.get("order_id")
        amount = decoded.get("amount")
        currency = decoded.get("currency")

        # 🔍 отримуємо платіж з БД
        payment = await get_payment(order_id)

        if not payment:
            return {"status": "not_found"}

        # 🔁 захист від дублювання
        if payment["status"] == "success":
            return {"status": "already_processed"}

        # 💰 перевірка суми
        if amount != payment["amount"]:
            raise HTTPException(status_code=400, detail="Invalid amount")

        # 💱 перевірка валюти
        if currency != "UAH":
            raise HTTPException(status_code=400, detail="Invalid currency")

        # ✅ оновлюємо статус
        await mark_payment_success(order_id)

        # 🎁 бізнес-логіка (додаємо слот)
        await add_slot(payment["seller_id"], 1)

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LiqPay callback error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
