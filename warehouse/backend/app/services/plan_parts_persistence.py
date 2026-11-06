"""Write-ahead, replay-safe provider boundary. Never changes stock or finance."""

import hashlib, json, os, re
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, text, func
from app.models import PlanPartsResponse, now


class PersistenceError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


RESOURCES = ("brands", "models", "modifications", "categories", "articles", "ktype")
SENSITIVE = {
    "authorization",
    "password",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "email",
    "phone",
    "telephone",
    "customer",
    "address",
    "personal_data",
    "token",
    "secret",
    "api_token",
    "apitoken",
    "cookie",
    "set_cookie",
    "contact",
    "username",
    "customer_name",
    "contact_email",
    "contact_phone",
    "ip_address",
}


def costs():
    try:
        value = json.loads(os.getenv("WAREHOUSE_PLAN_PARTS_TOKEN_MAXIMA", "{}"))
        return {
            k: v
            for k, v in value.items()
            if k in RESOURCES and type(v) is int and 0 <= v <= 10000
        }
    except (ValueError, AttributeError):
        return {}


def policy():
    return dict(
        terms_confirmed=os.getenv(
            "WAREHOUSE_PLAN_PARTS_STORAGE_APPROVED", "false"
        ).lower()
        == "true",
        max_tokens=costs(),
        oem_available=False,
        oem_reason="Метод і тариф OEM не підтверджені; aftermarket-артикул не є OEM",
        external_documentation_verified=False,
    )


def safe_body(raw):
    """Keep unknown public fields; remove known credential/PII keys before durable capture."""
    secret = os.getenv("PLAN_PARTS_API_KEY", "").encode()
    redacted = bool(secret and secret in raw)
    if secret:
        raw = raw.replace(secret, b"[REDACTED]")
    try:
        body = json.loads(raw)

        def scrub(v, depth=0):
            nonlocal redacted
            if depth > 60:
                raise ValueError("Payload nesting exceeds limit")
            if isinstance(v, dict):
                out = {}
                for k, value in v.items():
                    if re.sub(r"[- ]", "_", k.casefold()) in SENSITIVE:
                        redacted = True
                        out[k] = "[REDACTED]"
                    else:
                        out[k] = scrub(value, depth + 1)
                return out
            if isinstance(v, list):
                return [scrub(x, depth + 1) for x in v]
            if isinstance(v, str):
                cleaned = re.sub(
                    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED]", v
                )
                if cleaned != v:
                    redacted = True
                return cleaned
            return v

        clean = scrub(body)
        if redacted:
            raw = json.dumps(clean, ensure_ascii=False, separators=(",", ":")).encode()
    except (ValueError, RecursionError, UnicodeError):
        # Preserve malformed catalogue text for later parser repair, without literal credentials.
        original = raw
        keys = "|".join(re.escape(k) for k in SENSITIVE)
        raw = re.sub(
            rb'(?i)("(?:' + keys.encode() + rb')"\s*:\s*)"(?:\\.|[^"\\])*"',
            rb'\1"[REDACTED]"',
            raw,
        )
        raw = re.sub(
            rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", b"[REDACTED]", raw
        )
        redacted = redacted or raw != original
    return raw, redacted


class ResponseStore:
    def __init__(
        self,
        db,
        who,
        vehicle_id=None,
        request_key=None,
        confirm=False,
        max_tokens=None,
        force=False,
    ):
        self.db = db
        self.who = who
        self.vehicle_id = vehicle_id
        self.request_key = request_key
        self.confirm = confirm
        self.max_tokens = max_tokens
        self.force = force
        self.current = None
        self.last_metadata = {}

    def context(self, resource, params):
        if resource not in RESOURCES:
            raise PersistenceError(422, "Невідомий ресурс Plan.Parts")
        raw = json.dumps(
            [self.who.workspace_account_id, resource, params],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def recover(self, resource, params, cache_only=False):
        ctx = self.context(resource, params)
        query = select(PlanPartsResponse).where(
            PlanPartsResponse.account_id == self.who.workspace_account_id,
            PlanPartsResponse.context_hash == ctx,
        )
        if self.request_key:
            same = self.db.scalar(
                select(PlanPartsResponse).where(
                    PlanPartsResponse.account_id == self.who.workspace_account_id,
                    PlanPartsResponse.request_key == self.request_key,
                )
            )
            if same:
                if same.context_hash != ctx:
                    raise PersistenceError(
                        409, "Ключ запиту використано з іншим контекстом"
                    )
                if same.body is None:
                    raise PersistenceError(
                        409,
                        "Попередній запит невизначений або не завершений; платний повтор заблоковано",
                    )
                self.current = same
                return self._body(same)
        if self.force and not cache_only:
            return None
        row = self.db.scalar(
            query.where(
                PlanPartsResponse.body.is_not(None),
                PlanPartsResponse.http_status == 200,
            )
            .order_by(PlanPartsResponse.received_at.desc(), PlanPartsResponse.id)
            .limit(1)
        )
        if not row:
            return None
        self.current = row
        return self._body(row)

    def _body(self, row):
        if hashlib.sha256(row.body).hexdigest() != row.sha256:
            raise PersistenceError(
                409, "Контрольна сума збереженої відповіді не збігається"
            )
        self.last_metadata = {
            **row.metadata_json,
            "response_id": row.id,
            "received_at": row.received_at.isoformat() if row.received_at else None,
            "from_postgres": True,
        }
        return row.body

    def reserve(self, resource, params):
        ctx = self.context(resource, params)
        if not self.db.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": int(ctx[:15], 16)}
        ):
            raise PersistenceError(
                409, "Цей запит уже приймається; повторіть із тим самим ключем"
            )
        pending = self.db.scalar(
            select(PlanPartsResponse).where(
                PlanPartsResponse.account_id == self.who.workspace_account_id,
                PlanPartsResponse.context_hash == ctx,
                PlanPartsResponse.status.in_(["pending", "uncertain"]),
            )
        )
        if pending:
            raise PersistenceError(
                409,
                "Є незавершений запит; нова оплата заблокована. Перевірте збережені дані.",
            )
        p = policy()
        cost = p["max_tokens"].get(resource)
        if (
            self.who.user.role != "DIRECTOR"
            or self.who.actor_id != self.who.workspace_account_id
        ):
            raise PersistenceError(403, "Нові API-запити доступні лише власнику")
        if not p["terms_confirmed"] or cost is None:
            raise PersistenceError(
                503,
                "Права збереження або максимальна вартість Plan.Parts не підтверджені. Доступне відновлення збережених даних.",
            )
        if (
            not self.request_key
            or not self.confirm
            or self.max_tokens is None
            or self.max_tokens < cost
        ):
            raise PersistenceError(
                428,
                "Підтвердьте новий запит, його максимальну вартість та ключ повтору",
            )
        try:
            UUID(self.request_key)
        except (ValueError, TypeError):
            raise PersistenceError(422, "Недійсний ключ запиту") from None
        row = PlanPartsResponse(
            account_id=self.who.workspace_account_id,
            actor_id=self.who.actor_id,
            vehicle_id=self.vehicle_id,
            resource=resource,
            parameters=params,
            context_hash=ctx,
            request_key=self.request_key,
            status="pending",
            estimated_max_tokens=cost,
            metadata_json={},
        )
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise PersistenceError(
                409, "Запит уже зареєстровано; перечитайте результат з тим самим ключем"
            ) from None
        self.current = row

    def received(self, raw, status):
        if not self.current:
            raise PersistenceError(409, "Немає збереженого наміру запиту")
        raw, redacted = safe_body(raw)
        if len(raw) > 2097152:
            raise PersistenceError(502, "Відповідь перевищує ліміт сховища")
        row = self.db.get(PlanPartsResponse, self.current.id)
        row.body = raw
        row.sha256 = hashlib.sha256(raw).hexdigest()
        row.http_status = status
        row.received_at = now()
        row.status = "received" if status == 200 else "rejected"
        row.metadata_json = {
            "redacted": redacted,
            "returned_count": None,
            "completeness": "unknown",
        }
        self.db.commit()
        self.current = row
        self._body(row)
        return raw

    def parsed(self, rows, raw):
        if not self.current:
            return
        row = self.db.get(PlanPartsResponse, self.current.id)
        try:
            body = json.loads(raw)
            envelope = body.get("data", {}) if isinstance(body, dict) else {}
            total = envelope.get("count")
            limit = envelope.get("limit")
        except (ValueError, AttributeError):
            total = limit = None
        complete = (
            "partial"
            if type(total) is int and total > len(rows)
            else "complete" if type(total) is int and total == len(rows) else "unknown"
        )
        row.status = "validated"
        row.normalized = [r.model_dump(mode="json") for r in rows]
        row.metadata_json = {
            **row.metadata_json,
            "returned_count": len(rows),
            "provider_total": total,
            "provider_limit": limit,
            "completeness": complete,
        }
        self.db.commit()
        self._body(row)

    def failed(self, status=None):
        self.db.rollback()
        if not self.current:
            return
        row = self.db.get(PlanPartsResponse, self.current.id)
        row.status = (
            "invalid"
            if row.body is not None and row.http_status == 200
            else "rejected" if status == 429 else "uncertain"
        )
        self.db.commit()
