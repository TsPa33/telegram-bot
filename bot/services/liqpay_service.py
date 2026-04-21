import base64
import json
import hashlib
import uuid


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
        conn,
        amount: int,
        description: str,
        server_url: str
    ):
        # 🔹 1. генеруємо order_id
        order_id = str(uuid.uuid4())

        # 🔹 2. записуємо в БД (ОСНОВНЕ ЩО У ТЕБЕ НЕ БУЛО)
        await conn.execute("""
            INSERT INTO payments (order_id, status)
            VALUES ($1, 'pending')
        """, order_id)

        # 🔹 3. формуємо payload
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

        json_data = json.dumps(payload)
        data = base64.b64encode(json_data.encode()).decode()
        signature = self._sign(data)

        # 🔹 4. повертаємо URL + order_id (ВАЖЛИВО)
        return {
            "url": f"{self.api_url}?data={data}&signature={signature}",
            "order_id": order_id
        }
