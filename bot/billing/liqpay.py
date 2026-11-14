"""LiqPay v7 candidate codec, sandbox only. No HTTP calls or settlement authority.

Documentation: https://www.liqpay.ua/doc/api/internet_acquiring/checkout
https://www.liqpay.ua/doc/api/callback
https://www.liqpay.ua/doc/api/information/status_payment
https://www.liqpay.ua/en/doc/api/testing

The official prose describes v7/SHA3-256; legacy SHA-1 examples are NOT accepted.
A real merchant contract and provider-issued test evidence are separate gates.
"""
from dataclasses import dataclass, field
from decimal import Decimal
import base64
import binascii
import hashlib
import hmac
import json
import re
from urllib.parse import urlsplit

from .catalogue import money_minor
from .models import BillingError

CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"
STATUS_URL = "https://www.liqpay.ua/api/request"
MAX_DATA = 65536
ORDER = re.compile(r"carpot-wh-sbx-[0-9a-f]{32}\Z")
PENDING = frozenset({"processing", "prepared", "wait_accept", "wait_secure", "3ds_verify",
                     "captcha_verify", "cvv_verify", "ivr_verify", "otp_verify",
                     "wait_qr", "cash_wait", "wait_card", "wait_sender", "wait_receiver"})


def _check_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 510 or any(ch.isspace() for ch in value):
        raise BillingError("Invalid configured HTTPS URL")
    try:
        u = urlsplit(value)
        if u.scheme != "https" or not u.hostname or u.username is not None or u.password is not None or u.fragment:
            raise BillingError("Invalid configured HTTPS URL")
        if u.port not in (None, 443):
            raise BillingError("Invalid configured HTTPS port")
    except ValueError as exc:
        raise BillingError("Invalid configured HTTPS URL") from exc
    return value


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise BillingError("Duplicate JSON field")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise BillingError("Non-finite JSON value")


@dataclass(frozen=True)
class SandboxContract:
    public_key: str
    private_key: str = field(repr=False)
    result_url: str
    server_url: str
    version: int = 7

    def __post_init__(self):
        if type(self.version) is not int or self.version != 7:
            raise BillingError("Only explicit candidate v7 profile supported")
        for value in (self.public_key, self.private_key):
            if not isinstance(value, str) or not re.fullmatch(r"sandbox_[A-Za-z0-9_-]{1,240}", value):
                raise BillingError("Only sandbox credentials supported")
        _check_url(self.result_url)
        _check_url(self.server_url)
        if self.result_url == self.server_url:
            raise BillingError("Result and server callback URLs must be separate")


@dataclass(frozen=True)
class CheckoutTerms:
    order_id: str
    amount_minor: int
    currency: str = "UAH"

    def __post_init__(self):
        if not isinstance(self.order_id, str) or not ORDER.fullmatch(self.order_id):
            raise BillingError("Invalid sandbox checkout order")
        if type(self.amount_minor) is not int or not 1 <= self.amount_minor <= 9_000_000_000_000_000:
            raise BillingError("Invalid integer money")
        if self.currency != "UAH":
            raise BillingError("UAH required")


@dataclass(frozen=True)
class VerifiedSandboxEvent:
    order_id: str
    payment_id: str | None
    provider_status: str
    classification: str
    digest: str
    amount_minor: int
    merchant: str
    environment: str = "sandbox"


class SandboxCodec:
    def __init__(self, contract: SandboxContract):
        if not isinstance(contract, SandboxContract):
            raise BillingError("Explicit sandbox contract required")
        self.contract = contract

    def signature(self, data: str) -> str:
        if not isinstance(data, str) or not 1 <= len(data) <= MAX_DATA or not data.isascii():
            raise BillingError("Invalid encoded LiqPay data")
        key = self.contract.private_key
        return base64.b64encode(hashlib.sha3_256((key + data + key).encode("ascii")).digest()).decode("ascii")

    def _signed(self, payload: dict) -> dict:
        data = base64.b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).decode("ascii")
        return {"data": data, "signature": self.signature(data)}

    def checkout(self, terms: CheckoutTerms) -> dict:
        # Fixed server-side amount; no user-supplied URL, action or description.
        amount = f"{terms.amount_minor // 100}.{terms.amount_minor % 100:02d}"
        payload = dict(version=7, public_key=self.contract.public_key, action="pay",
                       amount=amount, currency=terms.currency, order_id=terms.order_id,
                       description="CarPot Warehouse — тестова оплата", language="uk",
                       result_url=self.contract.result_url, server_url=self.contract.server_url)
        return {"url": CHECKOUT_URL, "method": "POST", **self._signed(payload)}

    def status_request(self, terms: CheckoutTerms) -> dict:
        payload = dict(version=7, public_key=self.contract.public_key, action="status", order_id=terms.order_id)
        return {"url": STATUS_URL, "method": "POST", **self._signed(payload)}

    def verify(self, data: str, signature: str) -> dict:
        expected = self.signature(data)
        if not isinstance(signature, str) or not signature.isascii() or len(signature) != len(expected) or not hmac.compare_digest(signature, expected):
            raise BillingError("Invalid LiqPay signature")
        try:
            raw = base64.b64decode(data, validate=True)
            if base64.b64encode(raw).decode("ascii") != data:
                raise BillingError("Noncanonical base64")
            payload = json.loads(raw.decode("utf-8"), parse_float=Decimal,
                                 parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError, binascii.Error, RecursionError) as exc:
            raise BillingError("Invalid signed LiqPay JSON") from exc
        if not isinstance(payload, dict):
            raise BillingError("Invalid signed LiqPay object")
        if payload.get("public_key") != self.contract.public_key or type(payload.get("version")) is not int or payload["version"] != 7:
            raise BillingError("Merchant or version mismatch")
        if payload.get("action") != "pay":
            raise BillingError("Unexpected payment action")
        order = payload.get("order_id")
        if not isinstance(order, str) or not ORDER.fullmatch(order):
            raise BillingError("Unknown checkout order format")
        return payload

    def correlate(self, data: str, signature: str, terms: CheckoutTerms) -> VerifiedSandboxEvent:
        payload = self.verify(data, signature)
        if payload["order_id"] != terms.order_id or payload.get("currency") != terms.currency:
            raise BillingError("Payment order or currency mismatch")
        amount = payload.get("amount")
        if type(amount) not in (str, int, Decimal):
            raise BillingError("Invalid payment amount")
        if money_minor(str(amount)) != terms.amount_minor:
            raise BillingError("Payment amount mismatch")
        status = payload.get("status")
        if not isinstance(status, str) or not 1 <= len(status) <= 80:
            raise BillingError("Invalid provider status")
        pid = payload.get("payment_id")
        if pid is not None:
            if type(pid) is int:
                if pid <= 0:
                    raise BillingError("Invalid payment identity")
                pid = str(pid)
            if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", pid):
                raise BillingError("Invalid payment identity")
        if status in {"success", "sandbox"}:
            if not pid:
                raise BillingError("Successful test event lacks payment identity")
            classification = "test_success"
        elif status in {"failure", "error"}:
            classification = "failed"
        elif status in PENDING:
            classification = "pending"
        else:
            # Includes reversed, subscribed, unsubscribed and unknown states.
            classification = "review"
        return VerifiedSandboxEvent(terms.order_id, pid, status, classification,
                                    hashlib.sha256(data.encode("ascii")).hexdigest(),
                                    terms.amount_minor, self.contract.public_key)
