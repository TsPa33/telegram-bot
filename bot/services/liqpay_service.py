import base64
import json
import hashlib
import uuid

from bot.database.repositories.payment_repo import create_payment


print("🔥 NEW LIQPAY SERVICE LOADED")


# ===== DESCRIPTIONS =====
DESCRIPTIONS = {
    "site": "Створення сайту на сервісі Carpot",
    "garage_1": "1 місце в гаражі",
    "garage_5": "5 місць в гаражі",
    "garage_10": "10 місць в гаражі",
}


class LiqPayService:

    def __init__(self, public_key: str, private_key: str):
        self.public_key = public_key
        self.private_key = private_key
        self.api_url = "https://www.liqpay.ua/api/3/checkout"

    def _sign(self, data: str) -> str:
        sign_string = self.private_key + data + self.private_key
        return base64.b64encode(
            hashlib.sha1(sign_string.encode()).digest()
        ).decode()

    def _get_description(self, product: str, amount: int) -> str:
        """
        Визначає правильний description для LiqPay
        """
        if product == "site":
            return DESCRIPTIONS["site"]

        if product == "garage":
            if amount == 99:
                return DESCRIPTIONS["garage_1"]
            elif amount == 199:
                return DESCRIPTIONS["garage_5"]
            elif amount == 299:
                return DESCRIPTIONS["garage_10"]

        return "Оплата послуги"

    async def create_payment(
        self,
        amount: int,
        server_url: str,
        seller_id: int,
        product: str
    ):
        order_id = str(uuid.uuid4())

        print("CREATE PAYMENT SELLER_ID:", seller_id)
        print("PRODUCT:", product)

        # ===== SAVE TO DB =====
        await create_payment(
            seller_id=seller_id,
            order_id=order_id,
            amount=amount,
            product=product
        )

        # ===== DESCRIPTION =====
        description = self._get_description(product, amount)

        # ===== PAYLOAD =====
        payload = {
            "public_key": self.public_key,
            "version": "3",
            "action": "pay",
            "amount": amount,
            "currency": "UAH",
            "description": description,  # ✔ чистий UX текст
            "order_id": order_id,
            "server_url": server_url,
            "sandbox": 1
        }

        json_data = json.dumps(payload)
        data = base64.b64encode(json_data.encode()).decode()
        signature = self._sign(data)

        return {
            "url": f"{self.api_url}?data={data}&signature={signature}",
            "order_id": order_id
        }
