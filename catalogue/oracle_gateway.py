"""Fail-closed, staging-only Oracle API gateway for CarPot Catalogue.

No direct MySQL connection and no automatic Warehouse OEM mutations.
"""
import json
import logging
import os
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query

MAX_BODY = 96 * 1024
logger = logging.getLogger("carpot.oracle_gateway")


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
    # Only this named Railway-private HTTP proxy is permitted. It CONNECTs to the
    # HTTPS Oracle URL; the application still authenticates the Oracle certificate.
    proxy = os.getenv("ORACLE_HTTP_PROXY", "")
    if proxy and proxy != "http://carpot-oracle-relay.railway.internal:1055":
        raise HTTPException(503, "Oracle private network proxy unavailable")
    return raw.rstrip("/"), secret, (proxy or None)


def _request(path, params, *, audit_summary=False, modification_lookup=False):
    base, secret, proxy = _settings()
    try:
        with httpx.Client(follow_redirects=False, trust_env=False, proxy=proxy,
                          timeout=httpx.Timeout(10.0, connect=8.0)) as client:
            with client.stream("GET", base + path, params=params,
                               headers={"X-Oracle-Adapter-Key": secret,
                                        "Accept": "application/json"}) as response:
                missing = modification_lookup and response.status_code == 404
                if response.status_code != 200 and not missing:
                    logger.warning("oracle_gateway_upstream_status status=%d", response.status_code)
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
        if missing:
            if value == {"detail": "Modification absent from requested catalogue"}:
                raise HTTPException(404, value["detail"])
            raise ValueError("Audit endpoint unavailable")
        if audit_summary:
            if not isinstance(value, dict) or not isinstance(value.get("categories"), list):
                raise ValueError("Unexpected audit summary")
            return value
        if not isinstance(value, dict) or type(value.get("truncated")) is not bool:
            raise ValueError("Unexpected adapter response")
        items = value.get("items")
        if not isinstance(items, list) or len(items) > 50:
            raise ValueError("Unexpected adapter result count")
        return value
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        # Log the exception CLASS only: errors can embed URLs, credentials or proxy internals.
        logger.warning("oracle_gateway_upstream_error kind=%s", type(exc).__name__)
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


def _vehicle_items(data, fields):
    """Require a complete, well-typed identity-only result, with no VIN claim."""
    if data.get("fitment_verified") is not False or data.get("vehicle_identity_only") is not True:
        raise HTTPException(503, "Invalid Oracle vehicle response")
    result = []
    for item in data["items"]:
        if not isinstance(item, dict):
            raise HTTPException(503, "Invalid Oracle vehicle response")
        entry = {}
        for key, kind in fields.items():
            value = item.get(key)
            if kind == "id":
                if type(value) is not int or value < 1:
                    raise HTTPException(503, "Invalid Oracle vehicle identity")
            elif kind == "name":
                if not isinstance(value, str) or not 1 <= len(value) <= 128:
                    raise HTTPException(503, "Invalid Oracle vehicle name")
            elif kind == "interval":
                if value is not None and (not isinstance(value, str) or len(value) > 32):
                    raise HTTPException(503, "Invalid Oracle vehicle interval")
            elif kind == "attr":
                if not isinstance(value, str) or not 1 <= len(value) <= 256:
                    raise HTTPException(503, "Invalid Oracle vehicle attribute")
            entry[key] = value
        result.append(entry)
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

    # Discovery only: source vehicle identities cannot be used to assert VIN
    # compatibility or request a plan until a verified source graph exists.
    @router.get("/vehicles/manufacturers")
    def makers(name: str = Query(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9 .-]+$"),
               kind: str = Query(pattern=r"^(passenger|commercial)$"),
               limit: int = Query(default=20, ge=1, le=50)):
        data = _request("/api/v1/oracle/vehicles/manufacturers",
                        {"name": name, "kind": kind, "limit": limit})
        items = _vehicle_items(data, {"id": "id", "name": "name"})
        return dict(source="oracle", kind=kind, items=items,
                    truncated=data["truncated"], vehicle_identity_only=True,
                    fitment_verified=False)

    @router.get("/vehicles/models")
    def models(manufacturer_id: int = Query(ge=1),
               kind: str = Query(pattern=r"^(passenger|commercial)$"),
               after: int = Query(default=0, ge=0),
               limit: int = Query(default=30, ge=1, le=50)):
        data = _request("/api/v1/oracle/vehicles/models",
                        {"manufacturer_id": manufacturer_id, "kind": kind,
                         "after": after, "limit": limit})
        items = _vehicle_items(data, {"id": "id", "name": "name",
                                      "construction_interval": "interval"})
        if any(item["id"] <= after for item in items):
            raise HTTPException(503, "Invalid Oracle vehicle pagination")
        next_after = data.get("next_after")
        if (data["truncated"] and (not items or type(next_after) is not int
                                  or next_after != items[-1]["id"])) or (
                                  not data["truncated"] and next_after is not None):
            raise HTTPException(503, "Invalid Oracle vehicle cursor")
        return dict(source="oracle", manufacturer_id=manufacturer_id, kind=kind,
                    items=items, truncated=data["truncated"], next_after=next_after,
                    vehicle_identity_only=True, fitment_verified=False)

    @router.get("/vehicles/modifications")
    def modifications(model_id: int = Query(ge=1),
                      kind: str = Query(pattern=r"^(passenger|commercial)$"),
                      after: int = Query(default=0, ge=0),
                      limit: int = Query(default=30, ge=1, le=50)):
        data = _request("/api/v1/oracle/vehicles/modifications",
                        {"model_id": model_id, "kind": kind,
                         "after": after, "limit": limit})
        items = _vehicle_items(data, {"id": "id", "model_id": "id",
                                      "name": "name", "construction_interval": "interval"})
        if any(item["model_id"] != model_id or item["id"] <= after for item in items):
            raise HTTPException(503, "Invalid Oracle modification identity")
        next_after = data.get("next_after")
        if (data["truncated"] and (not items or type(next_after) is not int
                                  or next_after != items[-1]["id"])) or (
                                  not data["truncated"] and next_after is not None):
            raise HTTPException(503, "Invalid Oracle modification cursor")
        return dict(source="oracle", model_id=model_id, kind=kind, items=items,
                    truncated=data["truncated"], next_after=next_after,
                    vehicle_identity_only=True, fitment_verified=False)

    @router.get("/vehicles/attributes")
    def attributes(car_id: int = Query(ge=1),
                   kind: str = Query(pattern=r"^(passenger|commercial)$"),
                   limit: int = Query(default=50, ge=1, le=50)):
        data = _request("/api/v1/oracle/vehicles/attributes",
                        {"car_id": car_id, "kind": kind, "limit": limit})
        items = _vehicle_items(data, {"attribute_type": "attr", "display_value": "attr"})
        return dict(source="oracle", source_modification_id=car_id, kind=kind,
                    items=items, truncated=data["truncated"],
                    vehicle_identity_only=True, fitment_verified=False)

    def vehicle_audit_request(car_id, kind, endpoint, **pagination):
        data = _request(f"/api/v1/oracle/vehicles/{car_id}/{endpoint}",
                        {"kind": kind, **pagination}, audit_summary=endpoint == "audit",
                        modification_lookup=True)
        if (data.get("source") != "oracle" or data.get("source_modification_id") != car_id
                or data.get("kind") != kind or data.get("fitment_verified") is not False
                or data.get("source_association_only") is not True
                or type(data.get("manufacturer_id")) is not int or data["manufacturer_id"] < 1):
            raise HTTPException(503, "Invalid Oracle audit identity")
        if pagination:
            limit = pagination["limit"]
            expected = pagination["offset"] + limit if data["truncated"] else None
            if (len(data["items"]) > limit or (data["truncated"] and len(data["items"]) != limit)
                    or data.get("next_offset") != expected):
                raise HTTPException(503, "Invalid Oracle audit page")
        return data

    @router.get("/vehicles/{car_id}/audit")
    def vehicle_audit(kind: Literal["passenger", "commercial"], car_id: int = Path(ge=1)):
        return vehicle_audit_request(car_id, kind, "audit")

    @router.get("/vehicles/{car_id}/articles")
    def vehicle_articles(kind: Literal["passenger", "commercial"], car_id: int = Path(ge=1),
                         offset: int = Query(default=0, ge=0, le=2147483647),
                         limit: int = Query(default=20, ge=1, le=50)):
        return vehicle_audit_request(car_id, kind, "articles", offset=offset, limit=limit)

    @router.get("/vehicles/{car_id}/oem")
    def vehicle_oem(kind: Literal["passenger", "commercial"], car_id: int = Path(ge=1),
                    offset: int = Query(default=0, ge=0, le=2147483647),
                    limit: int = Query(default=20, ge=1, le=50)):
        return vehicle_audit_request(car_id, kind, "oem", offset=offset, limit=limit)

    return router
