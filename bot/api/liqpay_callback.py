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
        # 🔥 ПІДТРИМКА ДВОХ ТИПІВ (ВАЖЛИВО)
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            body = await request.json()
            data = body.get("data")
            signature = body.get("signature")
        else:
            form = await request.form()
            data = form.get("data")
            signature = form.get("signature")

        if not data or not signature:
            raise HTTPException(status_code=400, detail="Invalid request")

        # 🔐 перевірка підпису
        if not verify_signature(data, signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

        # 📦 decode
        decoded = json.loads(base64.b64decode(data).decode())
        logger.info(f"LiqPay callback: {decoded}")

        # тільки success
        if decoded.get("status") != "success":
            return {"status": "ignored"}

        order_id = decoded.get("order_id")
        amount = decoded.get("amount")
        currency = decoded.get("currency")

        payment = await get_payment(order_id)

        if not payment:
            return {"status": "not_found"}

        # idempotency
        if payment["status"] == "success":
            return {"status": "already_processed"}

        # перевірки
        if amount != payment["amount"]:
            raise HTTPException(status_code=400, detail="Invalid amount")

        if currency != "UAH":
            raise HTTPException(status_code=400, detail="Invalid currency")

        # update
        await mark_payment_success(order_id)
        await add_slot(payment["seller_id"], 1)

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LiqPay callback error: {str(e)}")
        return {"error": str(e)}
