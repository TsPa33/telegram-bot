"""Short-lived capability for Telegram URL buttons. Only opens an existing hosted POST."""

import hashlib, hmac, re, time, html
from .liqpay import _check_url
from .models import BillingError


class HostedLinks:
    def __init__(self, origin, key, environment):
        _check_url(origin)
        if len(key) < 32 or "?" in origin or "#" in origin:
            raise BillingError("Explicit hosted link configuration required")
        self.origin, self.key, self.environment = origin.rstrip("/"), key, environment

    def signature(self, order, expiry):
        return hmac.new(
            self.key, f"{self.environment}:{order}:{expiry}".encode(), hashlib.sha256
        ).hexdigest()

    def url(self, order, expiry):
        expiry = int(expiry.timestamp())
        return f"{self.origin}/pay/{order}.{expiry}.{self.signature(order, expiry)}"

    def verify(self, token):
        if not re.fullmatch(
            r"carpot-(sandbox|production)-[a-f0-9]{32}\.[0-9]{10}\.[a-f0-9]{64}", token
        ):
            raise BillingError("Invalid checkout link")
        order, expiry, signature = token.split(".")
        if (
            int(expiry) <= time.time()
            or not order.startswith("carpot-" + self.environment + "-")
            or not hmac.compare_digest(signature, self.signature(order, int(expiry)))
        ):
            raise BillingError("Expired checkout link")
        return order

    @staticmethod
    def document(form, sandbox):
        if (
            form.get("url") != "https://www.liqpay.ua/api/3/checkout"
            or form.get("method") != "POST"
        ):
            raise BillingError("Hosted form required")
        hidden = "".join(
            f'<input type="hidden" name="{name}" value="{html.escape(form[name], quote=True)}">'
            for name in ("data", "signature")
        )
        return (
            '<!doctype html><html lang="uk"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Оплата CarPot</title><h1>Оплата CarPot</h1>'
            + (
                "<p>Тестове середовище. Реальні кошти не списуються.</p>"
                if sandbox
                else ""
            )
            + '<p>Платіжні реквізити вводяться лише на офіційній сторінці LiqPay.</p><form method="post" action="https://www.liqpay.ua/api/3/checkout">'
            + hidden
            + '<button type="submit">Оплатити через LiqPay</button></form></html>'
        )
