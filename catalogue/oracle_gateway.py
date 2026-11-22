"""Fail-closed, staging-only Oracle API gateway for CarPot Catalogue.

No direct MySQL connection and no automatic Warehouse OEM mutations.
"""
import json
import os
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

MAX_BODY = 96 * 1024


def _settings():
    if os.getenv("ORACLE_CATALOGUE_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Oracle catalogue preview disabled")
    if os.getenv("RAILWAY_ENVIRONMENT_NAME") != "catalogue-staging":
        raise HTTPException(503, "Oracle catalogue preview restricted to staging")
    raw = os.getenv("ORACLE_ADAPTER_URL", "")
    secret = os.getenv("ORACLE_ADAPTER_KEY", "")
    parts = urlsplit(raw)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ("", "/") or not secret):
        raise HTTPException(503, "Oracle adapter connection unavailable")
    return raw.rstrip("/"), secret


def _request(path, params):
    base, secret = _settings()
    try:
        with httpx.Client(follow_redirects=False, trust_env=False,
                          timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            with client.stream("GET", base + path, params=params,
                               headers={"X-Oracle-Adapter-Key": secret,
                                        "Accept": "application/json"}) as response:
                if response.status_code != 200:
                    raise ValueError("Remote adapter is unavailable")
                if "application/json" not in response.headers.get("content-type", ""):
                    raise ValueError("Adapter returned non-JSON")
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BODY:
                        raise ValueError("Adapter response too large")
                    chunks.append(chunk)
        value = json.loads(b"".join(chunks))
        if not isinstance(value, dict) or type(value.get("truncated")) is not bool:
            raise ValueError("Unexpected adapter response")
        items = value.get("items")
        if not isinstance(items, list) or len(items) > 50:
            raise ValueError("Unexpected adapter result count")
        return value
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        raise HTTPException(503, "Oracle catalogue unavailable") from None


def _validated_items(data, fields):
    result = []
    for item in data["items"]:
        if not isinstance(item, dict):
            raise HTTPException(503, "Invalid Oracle catalogue response")
        output = {}
        for key, kind in fields.items():
            value = item.get(key)
            if kind == "text":
                if not isinstance(value, str) or not value or len(value) > 64:
                    raise HTTPException(503, "Invalid Oracle catalogue response")
            elif type(value) is not int or value < 1:
                raise HTTPException(503, "Invalid Oracle catalogue response")
            output[key] = value
        result.append(output)
    return result


def build_router(catalogue_auth):
    router = APIRouter(prefix="/api/v1/oracle", tags=["Oracle preview"],
                       dependencies=[Depends(catalogue_auth)])

    @router.get("/oem/by-article")
    def by_article(supplier_id: int = Query(ge=1, le=65535),
                   article_number: str = Query(min_length=1, max_length=64),
                   manufacturer_id: int = Query(ge=1),
                   limit: int = Query(default=20, ge=1, le=50)):
        data = _request("/api/v1/oracle/oem/by-article",
                        {"supplier_id": supplier_id, "article_number": article_number,
                         "manufacturer_id": manufacturer_id, "limit": limit})
        items = _validated_items(data, {"oem_number": "text"})
        return {"source": "oracle", "supplier_id": supplier_id,
                "article_number": article_number, "manufacturer_id": manufacturer_id,
                "items": items, "truncated": data["truncated"], "fitment_verified": False}

    @router.get("/oem/by-number")
    def by_number(manufacturer_id: int = Query(ge=1),
                  oem_number: str = Query(min_length=1, max_length=64),
                  limit: int = Query(default=20, ge=1, le=50)):
        data = _request("/api/v1/oracle/oem/by-number",
                        {"manufacturer_id": manufacturer_id, "oem_number": oem_number,
                         "limit": limit})
        items = _validated_items(data, {"supplier_id": "int", "article_number": "text"})
        return {"source": "oracle", "manufacturer_id": manufacturer_id,
                "oem_number": oem_number, "items": items,
                "truncated": data["truncated"], "cross_reference_only": True,
                "fitment_verified": False}

    @router.get("/vehicles/{car_id}/prd")
    def car_prd(car_id: int, limit: int = Query(default=20, ge=1, le=50)):
        if car_id < 1:
            raise HTTPException(422, "Invalid modification ID")
        data = _request(f"/api/v1/oracle/vehicles/{car_id}/prd", {"limit": limit})
        items = _validated_items(data, {"node_id": "int", "product_id": "int",
                                        "supplier_id": "int"})
        return {"source": "oracle", "source_modification_id": car_id,
                "items": items, "truncated": data["truncated"],
                "source_association_only": True, "fitment_verified": False}

    return router
