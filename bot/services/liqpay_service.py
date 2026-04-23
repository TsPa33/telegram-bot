import base64
import json
import hashlib
import uuid

from bot.database.repositories.payment_repo import create_payment


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

    async def create_payment(
        self,
        amount: int,
        description: str,
        server_url: str,
        seller_id: int
    ):
        # 🔹 order_id
        order_id = str(uuid.uuid4())

        # 🔍 DEBUG (можеш залишити на час тестів)
        print("CREATE PAYMENT SELLER_ID:", seller_id)

        # ✅ ЄДИНИЙ правильний спосіб запису в БД
        await create_payment(
            seller_id=seller_id,
            order_id=order_id,
            amount=amount
        )

        # 🔹 LiqPay payload
        payload = {
            "public_key": self.public_key,
            "version": "3",
            "action": "pay",
            "amount": amount,
            "currency": "UAH",
            "description": description,
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
