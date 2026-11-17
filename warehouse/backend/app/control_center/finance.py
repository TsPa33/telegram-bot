"""Bounded financial reads only, no fallback to customer owner identity."""

import hashlib
import os
import re
from urllib.parse import urlsplit
import httpx
from sqlalchemy import select
from .models import SourceLink, now


def read_finance(db, company):
    link = db.scalar(
        select(SourceLink).where(
            SourceLink.company_id == company.id,
            SourceLink.system == "billing",
            SourceLink.status == "verified",
        )
    )
    if not link:
        return dict(
            state="unavailable", reason="no_verified_billing_binding", environment=None
        )
    if link.environment not in {"sandbox", "production"} or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,80}", link.source_id
    ):
        return dict(
            state="unavailable",
            reason="invalid_verified_binding",
            environment=link.environment,
        )
    expected_environment = (
        "production" if company.environment == "production" else "sandbox"
    )
    if link.environment != expected_environment:
        return dict(
            state="unavailable",
            reason="binding_environment_conflict",
            environment=link.environment,
        )
    url = os.getenv("CONTROL_CENTER_BILLING_URL", "")
    p = urlsplit(url)
    key = os.getenv("CONTROL_CENTER_BILLING_KEY", "")
    if (
        p.scheme != "https"
        or not p.hostname
        or p.username
        or p.password
        or p.query
        or p.fragment
        or p.path
        or len(key.encode()) < 32
    ):
        return dict(
            state="unavailable",
            reason="staff_finance_peer_not_configured",
            environment=link.environment,
        )
    from bot.billing.transport import Transport

    path = "/v1/staff/warehouse/" + link.source_id
    proof = Transport(
        key.encode(),
        "control-center",
        "billing-api",
        "billing.staff.read",
        environment=link.environment,
    ).sign(
        dict(
            method="GET",
            path=path,
            body_sha256=hashlib.sha256(b"").hexdigest(),
            workspace_id=company.workspace_id,
            binding_id=link.source_id,
            scope="warehouse.finance.read",
        )
    )
    try:
        with httpx.Client(
            timeout=httpx.Timeout(5, connect=2), follow_redirects=False
        ) as client:
            with client.stream(
                "GET",
                url + path,
                headers={
                    "Authorization": "Bearer " + proof,
                    "X-CarPot-Peer": "control-center",
                },
            ) as response:
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 200000:
                        raise ValueError()
                if response.status_code != 200:
                    raise ValueError()
                import json

                value = json.loads(data)
        if (
            value.get("environment") != link.environment
            or value.get("binding_id") != link.source_id
        ):
            raise ValueError()
        sections = ["invoices", "payments", "reversals", "reviews", "paid_periods"]
        if any(
            not isinstance(value.get(k), list) or len(value[k]) > 100 for k in sections
        ):
            raise ValueError()
        return dict(
            state="fresh",
            fetched_at=now().isoformat(),
            environment=link.environment,
            binding_id=link.source_id,
            coverage="bounded_latest_100_per_section",
            totals_available=False,
            **{k: value[k] for k in sections},
        )
    except (httpx.HTTPError, ValueError):
        return dict(
            state="unavailable",
            reason="billing_read_failed",
            environment=link.environment,
        )
