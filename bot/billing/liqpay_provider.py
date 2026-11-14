"""Explicit LiqPay protocol profiles. No version/algorithm negotiation or fallback."""

import base64
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib, hmac, json, re, time, threading
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import httpx
from .liqpay import (
    CHECKOUT_URL,
    STATUS_URL,
    MAX_DATA,
    PENDING,
    _check_url,
    _unique_object,
    _reject_constant,
)
from .catalogue import money_minor
from .models import BillingError


@dataclass(frozen=True)
class ProviderProfile:
    environment: str
    public_key: str
    private_key: str = field(repr=False)
    result_url: str = ""
    server_url: str = ""
    protocol: str = "v7-sha3-256"
    merchant_confirmed: bool = False
    live_enabled: bool = False
    network_enabled: bool = False
    reversals_confirmed: bool = False

    def __post_init__(self):
        if self.environment not in {"sandbox", "production"} or self.protocol not in {
            "v7-sha3-256",
            "v3-sha1",
        }:
            raise BillingError("Explicit supported provider profile required")
        if self.protocol == "v3-sha1" and not self.merchant_confirmed:
            raise BillingError("Legacy profile requires explicit merchant confirmation")
        if any(
            not isinstance(k, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", k)
            for k in (self.public_key, self.private_key)
        ):
            raise BillingError("Invalid provider credentials")
        if self.environment == "sandbox" and not all(
            k.startswith("sandbox_") for k in (self.public_key, self.private_key)
        ):
            raise BillingError("Sandbox credentials required")
        if self.environment == "production" and (
            not self.merchant_confirmed
            or not self.live_enabled
            or any(
                k.startswith("sandbox_") for k in (self.public_key, self.private_key)
            )
        ):
            raise BillingError(
                "Live payments blocked until merchant confirmation and explicit activation"
            )
        _check_url(self.result_url)
        _check_url(self.server_url)
        if self.result_url == self.server_url:
            raise BillingError("Separate result and callback required")

    @property
    def version(self):
        return 7 if self.protocol == "v7-sha3-256" else 3


@dataclass(frozen=True)
class Terms:
    order_id: str
    amount_minor: int
    currency: str = "UAH"

    def __post_init__(self):
        if not isinstance(self.order_id, str) or not re.fullmatch(
            r"carpot-(sandbox|production)-[0-9a-f]{32}", self.order_id
        ):
            raise BillingError("Invalid operational order namespace")
        if (
            type(self.amount_minor) is not int
            or not 0 < self.amount_minor <= 9_000_000_000_000_000
            or self.currency != "UAH"
        ):
            raise BillingError("Integer UAH money required")


@dataclass(frozen=True)
class VerifiedCharge:
    order_id: str
    transaction_id: str | None
    status: str
    raw_status: str
    digest: str
    amount_minor: int
    environment: str
    merchant: str
    currency: str = "UAH"

    @property
    def provider(self):
        return "liqpay/" + self.environment + "/" + self.merchant


class LiqPayProvider:
    def __init__(self, profile: ProviderProfile, *, transport=None, sleep=time.sleep):
        self.profile = profile
        self.transport = transport
        self.sleep = sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def signature(self, data):
        if (
            not isinstance(data, str)
            or not 0 < len(data) <= MAX_DATA
            or not data.isascii()
        ):
            raise BillingError("Invalid encoded payment")
        fn = (
            hashlib.sha3_256 if self.profile.protocol == "v7-sha3-256" else hashlib.sha1
        )
        key = self.profile.private_key
        return base64.b64encode(
            fn((key + data + key).encode("ascii")).digest()
        ).decode()

    def sign(self, payload):
        data = base64.b64encode(
            json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode()
        ).decode()
        return dict(data=data, signature=self.signature(data))

    def checkout(self, terms):
        self._namespace(terms)
        return dict(
            url=CHECKOUT_URL,
            method="POST",
            **self.sign(
                dict(
                    version=self.profile.version,
                    public_key=self.profile.public_key,
                    action="pay",
                    amount=f"{terms.amount_minor // 100}.{terms.amount_minor % 100:02d}",
                    currency="UAH",
                    order_id=terms.order_id,
                    description="Оплата сервісу CarPot",
                    language="uk",
                    result_url=self.return_url(terms.order_id),
                    server_url=self.profile.server_url,
                )
            ),
        )

    def return_url(self, order_id):
        url = urlsplit(self.profile.result_url)
        query = [(k, v) for k, v in parse_qsl(url.query) if k != "billing_order"]
        return urlunsplit(
            (
                url.scheme,
                url.netloc,
                url.path,
                urlencode(query + [("billing_order", order_id)]),
                "",
            )
        )

    def _namespace(self, terms):
        if not terms.order_id.startswith("carpot-" + self.profile.environment + "-"):
            raise BillingError("Payment environment mismatch")

    def decode_callback(self, data, signature):
        expected = self.signature(data)
        if (
            not isinstance(signature, str)
            or not signature.isascii()
            or not hmac.compare_digest(expected, signature)
        ):
            raise BillingError("Invalid LiqPay signature")
        try:
            raw = base64.b64decode(data, validate=True)
            if base64.b64encode(raw).decode() != data:
                raise ValueError()
            return self._json(raw)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise BillingError("Invalid signed payment") from exc

    @staticmethod
    def _json(raw):
        if len(raw) > MAX_DATA:
            raise BillingError("Provider response too large")
        value = json.loads(
            raw,
            parse_float=Decimal,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
        if not isinstance(value, dict):
            raise BillingError("Provider object required")
        return value

    def correlate(self, payload, terms, *, digest):
        self._namespace(terms)
        p = self.profile
        if (
            payload.get("public_key") != p.public_key
            or payload.get("version") not in (p.version, str(p.version))
            or type(payload.get("version")) not in (str, int)
        ):
            raise BillingError("Merchant or protocol mismatch")
        if (
            payload.get("order_id") != terms.order_id
            or payload.get("action") != "pay"
            or payload.get("currency") != "UAH"
        ):
            raise BillingError("Payment correlation failed")
        amount = payload.get("amount")
        if (
            type(amount) not in (str, int, Decimal)
            or money_minor(str(amount)) != terms.amount_minor
        ):
            raise BillingError("Payment amount mismatch")
        status = payload.get("status")
        pid = payload.get("payment_id")
        if not isinstance(status, str) or not re.fullmatch(
            r"[a-zA-Z0-9_]{1,80}", status
        ):
            raise BillingError("Invalid provider status")
        if type(pid) is int:
            pid = str(pid) if pid > 0 else None
        if pid is not None and (
            not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", pid)
        ):
            raise BillingError("Invalid provider transaction")
        if p.environment == "production" and (
            status == "sandbox" or str(payload.get("sandbox", "0")) == "1"
        ):
            raise BillingError("Sandbox event cannot activate production")
        classification = (
            "success"
            if status == "success" or p.environment == "sandbox" and status == "sandbox"
            else "failure"
            if status in {"failure", "error"}
            else "pending"
            if status in PENDING
            else "review"
        )
        if classification == "success" and not pid:
            raise BillingError("Successful payment lacks identity")
        return VerifiedCharge(
            terms.order_id,
            pid,
            classification,
            status,
            digest,
            terms.amount_minor,
            p.environment,
            p.public_key,
        )

    def query_status(self, terms):
        self._namespace(terms)
        if not self.profile.network_enabled or not self.profile.merchant_confirmed:
            raise BillingError(
                "Provider network blocked pending merchant sandbox confirmation"
            )
        with self._lock:
            delay = max(0, self._next - time.monotonic())
            if delay > 2:
                raise BillingError("Provider request rate exceeded")
            self._next = max(self._next, time.monotonic()) + 0.25
        if delay > 2:
            raise BillingError("Provider request rate exceeded")
        self.sleep(delay)
        form = self.sign(
            dict(
                version=self.profile.version,
                public_key=self.profile.public_key,
                action="status",
                order_id=terms.order_id,
            )
        )
        for attempt in range(3):
            try:
                with httpx.Client(
                    transport=self.transport,
                    timeout=httpx.Timeout(10, connect=3),
                    follow_redirects=False,
                ) as client:
                    with client.stream("POST", STATUS_URL, data=form) as response:
                        if response.status_code in (429, 500, 502, 503, 504):
                            if attempt == 2:
                                raise BillingError(
                                    "Provider status temporarily unavailable"
                                )
                            retry = response.headers.get("retry-after", "0")
                            self.sleep(
                                min(
                                    2,
                                    max(
                                        0.1 * 2**attempt,
                                        float(retry) if retry.isdigit() else 0,
                                    ),
                                )
                            )
                            continue
                        if response.status_code != 200:
                            raise BillingError("Provider status rejected")
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > MAX_DATA:
                                raise BillingError("Provider response too large")
                return self._json(bytes(raw)), hashlib.sha256(bytes(raw)).hexdigest()
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise BillingError("Provider status unavailable") from None
                self.sleep(0.1 * 2**attempt)
        raise BillingError("Provider status unavailable")
