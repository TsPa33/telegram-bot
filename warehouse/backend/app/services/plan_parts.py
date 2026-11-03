"""Explicit, bounded Plan.Parts requests. No cache, retries or background sync."""

import json
from copy import deepcopy
from collections import OrderedDict
import os
import re
from datetime import date
from threading import Lock
from time import monotonic

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

BASE_URL = "https://cdn.plan.parts/api"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class PlanPartsError(Exception):
    def __init__(self, status: int, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class Brand(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    brand: str = Field(min_length=1, max_length=200)
    mfa_id: int = Field(gt=0, strict=True)


class CatalogPartType(BaseModel):
    """Provider catalogue type; article_count is never inventory quantity."""
    pt_id: int = Field(gt=0, strict=True)
    name: str = Field(min_length=1, max_length=200)
    article_count: int = Field(ge=0, strict=True)



class Article(BaseModel):
    """Aftermarket article offer, NOT a unique part on a donor vehicle."""
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    art_id: int = Field(gt=0, strict=True)
    article_nr: str = Field(min_length=1, max_length=200)
    brand: str = Field(min_length=1, max_length=200)
    part_name: str = Field(min_length=1, max_length=400)
    img_url: str | None = None


class VehicleMatch(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    ktype: int = Field(gt=0, strict=True)
    brand: str | None = None
    modification: str = Field(min_length=1, max_length=200)
    year_from: int | None = None
    year_to: int | None = None
    power_kw: float | None = None
    power_ps: float | None = None

    @field_validator("year_from", "year_to", mode="before")
    @classmethod
    def normalize_year(cls, value):
        return production_year(value)

def provider_results(payload, selectors):
    """Validate the observed envelope and reject partial/mismatched responses."""
    if isinstance(payload, dict):
        if payload.get("success") is not True or not isinstance(payload.get("data"), dict):
            raise ValueError("Invalid provider envelope")
        envelope = payload["data"]
        payload = envelope.get("results")
        count = envelope.get("count")
        if not isinstance(payload, list) or (count is not None and (type(count) is not int or count != len(payload))):
            raise ValueError("Invalid or incomplete result count")
        for selector, expected in selectors.items():
            if selector in envelope and (type(envelope[selector]) is not type(expected) or envelope[selector] != expected):
                raise ValueError("Response selector does not match request")
        if "limit" in envelope and (type(envelope["limit"]) is not int
                or envelope["limit"] < 1 or len(payload) > envelope["limit"]):
            raise ValueError("Invalid provider limit")
    if not isinstance(payload, list) or len(payload) > 10000:
        raise ValueError("Unsupported response structure")
    return payload


class ModelOption(BaseModel):
    ms_id: int = Field(gt=0, strict=True)
    name: str | None = None
    year_from: int | None = None
    year_to: int | None = None

    @field_validator("year_from", "year_to", mode="before")
    @classmethod
    def normalize_year(cls, value):
        return production_year(value)

    @model_validator(mode="after")
    def valid_period(self):
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("Invalid model production period")
        return self


def production_year(value):
    if value is None:
        return None
    if type(value) is int and 1886 <= value <= 2100:
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", value):
        date.fromisoformat(value + ("-01-01" if len(value) == 4 else "-01" if len(value) == 7 else ""))
        year = int(value[:4])
        if 1886 <= year <= 2100:
            return year
    raise ValueError("Unsupported production year")


class Modification(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, allow_inf_nan=False)
    ktype: int = Field(gt=0, strict=True)
    modification: str = Field(min_length=1, max_length=200)
    model_series: str | None = Field(default=None, max_length=200)
    displacement_cc: float | None = Field(default=None, ge=0)
    power_kw: float | None = Field(default=None, ge=0)
    power_ps: float | None = Field(default=None, ge=0)
    year_from: int | None = None
    year_to: int | None = None

    @field_validator("year_from", "year_to", mode="before")
    @classmethod
    def normalize_year(cls, value):
        return production_year(value)

    @model_validator(mode="after")
    def valid_period(self):
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("Invalid production period")
        return self


def modifications_for_year(items: list[Modification], year: int | None):
    if year is None:
        return items
    # Unknown start years cannot establish compatibility. Null end = open-ended.
    return [m for m in items if m.year_from is not None and m.year_from <= year
            and (m.year_to is None or year <= m.year_to)]


class RequestGate:
    """Per-process attempt budget; failures count too. Never stores API data."""

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.lock = Lock()
        self.accounts = {}
        self.recent = []

    def acquire(self, account_id: str, operation: str = "brands"):
        # Short, explicit cooldown for each paid lookup and per-account rate
        # window. Retain protection against duplicate paid requests and bursts.
        with self.lock:
            now = self.clock()
            self.accounts = {k: v for k, v in self.accounts.items() if v > now}
            self.recent = [(a, t) for a, t in self.recent if t > now - 30]
            key = (account_id, operation)
            repeated = self.accounts.get(key, 0) > now
            recent_by_account = sum(a == account_id for a, _ in self.recent)
            if repeated or len(self.recent) >= 60 or recent_by_account >= 10:
                if repeated:
                    remaining = max(1, int(self.accounts[key] - now + 0.999))
                else:
                    relevant = self.recent if len(self.recent) >= 60 else [
                        (a, t) for a, t in self.recent if a == account_id
                    ]
                    remaining = max(1, int(30 - (now - min(t for _, t in relevant)) + 0.999))
                raise PlanPartsError(429, "Ліміт запитів CarPot. Повторіть через " + str(remaining) + " с", remaining)
            if len(self.accounts) >= 10000:
                raise PlanPartsError(429, "Ліміт запитів CarPot", 30)
            self.accounts[key] = now + 30
            self.recent.append((account_id, now))


request_gate = RequestGate()

# A transient per-workspace cache for internal use only; no provider catalogue is
# persisted to PostgreSQL, Redis, disk or sent to other accounts.
# Cache expires after 30 minutes and disappears on API restarts.
CACHE_TTL_SECONDS = 1800
CACHE_MAX_KEYS = 64
_cache_lock = Lock()
_result_cache = OrderedDict()


class PlanPartsClient:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def brands(self, account_id: str, gate: RequestGate = request_gate) -> list[Brand]:
        return self._lookup(account_id, "brands", {}, Brand, "mfa_id", gate)

    def models(self, account_id: str, mfa_id: int, gate: RequestGate = request_gate):
        # Confirmed by the uploaded Volkswagen 121 JSON export.
        field = os.getenv("PLAN_PARTS_MODEL_NAME_FIELD", "name").strip() or "name"
        return self._lookup(account_id, "models", {"mfa_id": mfa_id}, ModelOption, "ms_id", gate, field)

    def modifications(self, account_id: str, ms_id: int, gate: RequestGate = request_gate):
        return self._lookup(account_id, "modifications", {"ms_id": ms_id}, Modification, "ktype", gate)

    def categories(self, account_id: str, ktype: int, gate: RequestGate = request_gate):
        return self._lookup(account_id, "categories", {"ktype": ktype}, CatalogPartType, "pt_id", gate)

    def vehicle_matches(self, account_id: str, brand: str, model: str, year: int, gate: RequestGate = request_gate):
        if not brand.strip() or not model.strip() or not 1886 <= year <= 2100:
            raise PlanPartsError(422, "Уточніть марку, модель і рік автомобіля")
        return self._lookup(account_id, "ktype", {"brand": brand, "model": model, "year": year},
                            VehicleMatch, "ktype", gate, path="/v1/aftermarket/ktype")

    def articles(self, account_id: str, ktype: int, pt_id: int, gate: RequestGate = request_gate):
        return self._lookup(account_id, "articles", {"ktype": ktype, "pt_id": pt_id},
                            Article, "art_id", gate)

    def _lookup(self, account_id, resource, params, schema, identifier, gate, name_field="", path=None):
        # Cache only completed, validated responses, isolated by workspace,
        # provider resource, query and configured schema. A single lock prevents
        # concurrent identical paid requests from double-charging the same user.
        # Transports are isolated to avoid cross-contamination of test fixtures.
        if os.getenv("PLAN_PARTS_ENABLED", "false").lower() != "true":
            raise PlanPartsError(503, "Інтеграцію Plan.Parts не ввімкнено")
        key = os.getenv("PLAN_PARTS_API_KEY", "").strip()
        if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise PlanPartsError(503, "API-ключ Plan.Parts не налаштовано")
        cache_key = (account_id, resource, tuple(sorted(params.items())),
                     schema.__name__, name_field, path, id(self._transport) if self._transport else None)
        with _cache_lock:
            now = monotonic()
            for expired_key, (expires, _) in list(_result_cache.items()):
                if expires <= now:
                    del _result_cache[expired_key]
            existing = _result_cache.get(cache_key)
            if existing:
                _result_cache.move_to_end(cache_key)
                return deepcopy(existing[1])
            result = self._uncached_lookup(account_id, resource, params, schema, identifier, gate, name_field, path)
            if len(result) <= 10000:
                _result_cache[cache_key] = (monotonic() + CACHE_TTL_SECONDS, deepcopy(result))
                while len(_result_cache) > CACHE_MAX_KEYS:
                    _result_cache.popitem(last=False)
            return result

    def _uncached_lookup(self, account_id, resource, params, schema, identifier, gate, name_field="", path=None):
        if os.getenv("PLAN_PARTS_ENABLED", "false").lower() != "true":
            raise PlanPartsError(503, "Інтеграцію Plan.Parts не ввімкнено")
        key = os.getenv("PLAN_PARTS_API_KEY", "").strip()
        if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise PlanPartsError(503, "API-ключ Plan.Parts не налаштовано")
        gate.acquire(account_id, resource + str(sorted(params.items())) if params else resource)
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=httpx.Timeout(10, connect=5),
                follow_redirects=False,
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            ) as client:
                with client.stream("GET", BASE_URL + (path or "/v1/aftermarket/catalog/" + resource), params=params) as response:
                    if response.status_code == 429:
                        raise PlanPartsError(429, "Ліміт запитів постачальника Plan.Parts", 30)
                    if response.status_code != 200:
                        raise PlanPartsError(502, "Plan.Parts відхилив запит")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise PlanPartsError(502, "Відповідь Plan.Parts завелика")
            data = provider_results(json.loads(raw), {} if resource == 'ktype' else params)
            if schema is ModelOption:
                rows = []
                for item in data:
                    if not isinstance(item, dict):
                        raise ValueError("Invalid model record")
                    if "mfa_id" in item and (type(item["mfa_id"]) is not int or item["mfa_id"] != params["mfa_id"]):
                        raise ValueError("Model belongs to another brand")
                    name = item.get(name_field)
                    if not isinstance(name, str) or not name.strip() or len(name) > 100:
                        raise ValueError("Configured model name field missing")
                    rows.append(ModelOption.model_validate({"ms_id": item.get("ms_id"), "name": name,
                                "year_from": item.get("year_from"), "year_to": item.get("year_to")}))
            else:
                rows = [schema.model_validate(item) for item in data]
            if len({getattr(row, identifier) for row in rows}) != len(rows):
                raise ValueError("Duplicate identifier")
            return rows
        except httpx.TimeoutException:
            raise PlanPartsError(504, "Перевищено час очікування Plan.Parts") from None
        except httpx.HTTPError:
            raise PlanPartsError(502, "Plan.Parts тимчасово недоступний") from None
        except (ValueError, ValidationError):
            raise PlanPartsError(502, "Непідтримуваний формат відповіді Plan.Parts") from None
