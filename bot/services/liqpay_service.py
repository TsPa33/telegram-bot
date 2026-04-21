import base64
import json
import hashlib
import uuid


class LiqPayService:

    def __init__(self, public_key: str, private_key: str):
        if not public_key or not private_key:
            raise ValueError("LiqPay keys are missing")

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
        conn,
        amount: int,
        description: str,
        server_url: str
    ):
        # 🔹 1. Генеруємо order_id
        order_id = str(uuid.uuid4())

        # 🔹 2. Запис у БД
        await conn.execute("""
            INSERT INTO payments (order_id, amount, status)
            VALUES ($1, $2, 'pending')
        """, order_id, amount)

        # 🔹 3. Payload для LiqPay
        payload = {
            "public_key": self.public_key,
            "version": "3",
            "action": "pay",
            "amount": amount,
            "currency": "UAH",
            "description": description,
            "order_id": order_id,
            "server_url": server_url,
            "sandbox": 1  # тест режим
        }

        # 🔹 4. Кодування
        json_data = json.dumps(payload)
        data = base64.b64encode(json_data.encode()).decode()
        signature = self._sign(data)

        # 🔹 5. Формуємо URL
        payment_url = f"{self.api_url}?data={data}&signature={signature}"

        return {
            "url": payment_url,
            "order_id": order_id
        }
