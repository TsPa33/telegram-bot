"""Authenticated local integration contract. No production credentials or HTTP exposure."""

import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4
from .models import BillingError


class Transport:
    def __init__(self, key: bytes, issuer: str, audience: str, scope: str):
        if len(key) < 32:
            raise BillingError("At least 32 random key bytes required")
        self.key, self.issuer, self.audience, self.scope = key, issuer, audience, scope

    def sign(self, payload, *, now=None):
        stamp = int(time.time() if now is None else now)
        envelope = dict(
            iss=self.issuer,
            aud=self.audience,
            scope=self.scope,
            iat=stamp,
            exp=stamp + 60,
            jti=str(uuid4()),
            environment="test",
            payload=payload,
        )
        raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        data = base64.urlsafe_b64encode(raw).decode()
        return (
            data + "." + hmac.new(self.key, data.encode(), hashlib.sha256).hexdigest()
        )

    def verify(self, token, *, now=None):
        if not isinstance(token, str) or len(token) > 200000:
            raise BillingError("Invalid transport token")
        try:
            data, signature = token.split(".")
            expected = hmac.new(self.key, data.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError()
            e = json.loads(base64.b64decode(data, altchars=b"-_", validate=True))
            stamp = int(time.time() if now is None else now)
            if (
                e["iss"] != self.issuer
                or e["aud"] != self.audience
                or e["scope"] != self.scope
                or e["environment"] != "test"
                or type(e["iat"]) is not int
                or type(e["exp"]) is not int
                or not e["iat"] <= stamp < e["exp"]
                or e["exp"] - e["iat"] > 60
                or not isinstance(e["jti"], str)
                or len(e["jti"]) != 36
            ):
                raise ValueError()
            return e
        except (ValueError, KeyError, TypeError) as exc:
            raise BillingError("Transport authentication failed") from exc
