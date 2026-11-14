"""Product SDK: authenticated service calls, bounded replies, no provider or DB credentials."""

import hashlib, json
import httpx
from .transport import Transport
from .liqpay import _check_url
from .models import BillingError


class BillingClient:
    def __init__(self, url, key, peer, environment, *, transport=None):
        _check_url(url)
        if len(key) < 32 or "?" in url or "#" in url:
            raise BillingError("Explicit Billing peer configuration required")
        self.url, self.key, self.peer, self.environment, self.transport = (
            url.rstrip("/"),
            key,
            peer,
            environment,
            transport,
        )

    async def request(self, method, path, claims, body=None):
        if not path.startswith("/v1/") or "?" in path or ".." in path:
            raise BillingError("Invalid Billing path")
        raw = (
            json.dumps(body, separators=(",", ":")).encode()
            if body is not None
            else b""
        )
        scoped = dict(
            claims,
            method=method,
            path=path,
            body_sha256=hashlib.sha256(raw).hexdigest(),
        )
        proof = Transport(
            self.key,
            self.peer,
            "billing-api",
            "billing.session",
            environment=self.environment,
        ).sign(scoped)
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(15, connect=3),
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    method,
                    self.url + path,
                    content=raw,
                    headers={
                        "Authorization": "Bearer " + proof,
                        "X-CarPot-Peer": self.peer,
                        "Content-Type": "application/json",
                    },
                ) as response:
                    if response.status_code != 200:
                        raise BillingError("Billing operation unavailable")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 262144:
                            raise BillingError("Billing reply too large")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise BillingError("Invalid Billing reply")
            return result
        except (httpx.HTTPError, ValueError) as exc:
            raise BillingError("Billing temporarily unavailable") from exc
