"""Explicit, bounded Plan.Parts requests. No cache, retries or background sync."""

import json
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
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Brand(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    brand: str = Field(min_length=1, max_length=200)
    mfa_id: int = Field(gt=0, strict=True)


class CatalogPartType(BaseModel):
    """Provider catalogue type; article_count is never inventory quantity."""
    pt_id: int = Field(gt=0, strict=True)
    name: str = Field(min_length=1, max_length=200)
    article_count: int = Field(ge=0, strict=True)


def provider_results(payload, selectors):
    """Validate the observed envelope and reject partial/mismatched responses."""
    if isinstance(payload, dict):
        if payload.get("success") is not True or not isinstance(payload.get("data"), dict):
            raise ValueError("Invalid provider envelope")
        envelope = payload["data"]
        payload = envelope.get("results")
        count = envelope.get("count")
        if not isinstance(payload, list) or type(count) is not int or count != len(payload):
            raise ValueError("Invalid or incomplete result count")
        for selector, expected in selectors.items():
            if type(envelope.get(selector)) is not int or envelope[selector] != expected:
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
        with self.lock:
            now = self.clock()
            self.accounts = {k: v for k, v in self.accounts.items() if v > now}
            self.recent = [(a, t) for a, t in self.recent if t > now - 60]
            key = (account_id, operation)
            if (self.accounts.get(key, 0) > now or len(self.recent) >= 60
                    or sum(a == account_id for a, _ in self.recent) >= 10):
                raise PlanPartsError(429, "Ліміт запитів Plan.Parts. Спробуйте пізніше")
            if len(self.accounts) >= 10000:
                raise PlanPartsError(429, "Ліміт запитів Plan.Parts")
            self.accounts[key] = now + 60
            self.recent.append((account_id, now))


request_gate = RequestGate()


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

    def _lookup(self, account_id, resource, params, schema, identifier, gate, name_field=""):
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
                with client.stream("GET", BASE_URL + "/v1/aftermarket/catalog/" + resource, params=params) as response:
                    if response.status_code == 429:
                        raise PlanPartsError(429, "Ліміт запитів постачальника Plan.Parts")
                    if response.status_code != 200:
                        raise PlanPartsError(502, "Plan.Parts відхилив запит")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise PlanPartsError(502, "Відповідь Plan.Parts завелика")
            data = provider_results(json.loads(raw), params)
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
