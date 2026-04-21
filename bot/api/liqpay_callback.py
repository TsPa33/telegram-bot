import base64
import json
import hashlib

from fastapi import APIRouter, Request, HTTPException

from bot.database.repositories.payment_repo import get_payment, mark_payment_success
from bot.database.repositories.seller_repo import add_slot
from bot.config import LIQPAY_PRIVATE_KEY

router = APIRouter()


def verify_signature(data: str, signature: str) -> bool:
    sign_string = LIQPAY_PRIVATE_KEY + data + LIQPAY_PRIVATE_KEY
    expected = base64.b64encode(hashlib.sha1(sign_string.encode()).digest()).decode()
    return expected == signature


@router.post("/liqpay/callback")
async def liqpay_callback(request: Request):
    form = await request.form()

    data = form.get("data")
    signature = form.get("signature")

    if not data or not signature:
        raise HTTPException(status_code=400, detail="Invalid request")

    if not verify_signature(data, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    decoded = json.loads(base64.b64decode(data).decode())

    if decoded.get("status") != "success":
        return {"status": "ignored"}

    order_id = decoded.get("order_id")

    payment = await get_payment(order_id)

    if not payment:
        return {"status": "not_found"}

    if payment["status"] == "success":
        return {"status": "already_processed"}

    await mark_payment_success(order_id)
    await add_slot(payment["seller_id"], 1)

    return {"status": "ok"}
