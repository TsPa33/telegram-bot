"""Bounded HTTPS source adapter; no Warehouse DB credential in CRM."""
import json
import os
import time
from datetime import datetime
from urllib.parse import urlsplit
import httpx
from app.services.control_transport import signature, PATH
from .config import environment

def fetch_batch(cursor, limit):
    url = os.environ["CONTROL_CENTER_WAREHOUSE_SOURCE_URL"]
    p = urlsplit(url)
    key = os.environ["CONTROL_CENTER_WAREHOUSE_SOURCE_KEY"]
    if environment() != "staging" or p.scheme != "https" or not p.hostname or p.username or p.password or p.path or p.query or p.fragment or len(key) < 32:
        raise RuntimeError("Invalid source configuration")
    limit = min(limit, 50)
    stamp = str(int(time.time()))
    with httpx.Client(timeout=httpx.Timeout(10, connect=3), follow_redirects=False) as http:
        with http.stream("GET", url + PATH, params={"cursor": cursor or "", "limit": limit},
                         headers={"X-Control-Stamp": stamp, "X-Control-Signature": signature(key, stamp, cursor, limit)}) as response:
            if response.status_code != 200:
                raise RuntimeError("Source unavailable")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 4_000_000:
                    raise RuntimeError("Source response too large")
    value = json.loads(raw)
    rows, next_cursor = value["records"], value["next_cursor"]
    if value["environment"] != "staging" or not isinstance(rows, list) or len(rows) > limit or (next_cursor is not None and (not isinstance(next_cursor, str) or len(next_cursor)>160 or next_cursor==cursor)):
        raise RuntimeError("Invalid source response")
    for row in rows:
        if row["snapshot"]["source_environment"] != "staging":
            raise RuntimeError("Source environment mismatch")
        row["registered_at"] = datetime.fromisoformat(row["registered_at"])
    return rows, next_cursor
