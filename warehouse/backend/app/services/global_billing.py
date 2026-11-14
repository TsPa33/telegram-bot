"""Warehouse is a consumer, never a finance DB client. Off without explicit rollout."""

import hashlib, json, os
from urllib.parse import urlsplit
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from app.models.entitlements import EntitlementWorkspace, EntitlementReceipt


def enabled():
    return os.getenv("WAREHOUSE_GLOBAL_BILLING_ENABLED") == "true"


def environment():
    value = os.getenv("WAREHOUSE_BILLING_ENVIRONMENT")
    host_environment = os.getenv("WAREHOUSE_ENV", "local")
    if (
        value not in {"sandbox", "production"}
        or value == "production"
        and host_environment != "production"
        or value == "sandbox"
        and host_environment not in {"local", "staging"}
    ):
        raise HTTPException(503, "Середовище оплати потребує окремого налаштування")
    return value


def transport(issuer, audience, scope):
    # Lazy SDK import keeps all existing Warehouse images/flags OFF compatible.
    if not enabled():
        raise HTTPException(503, "Централізований Billing вимкнено")
    key = os.getenv("WAREHOUSE_BILLING_SERVICE_KEY", "").encode()
    if len(key) < 32:
        raise HTTPException(503, "Billing service authentication не налаштовано")
    from bot.billing.transport import Transport

    return Transport(key, issuer, audience, scope, environment=environment())


def request(who, method, path, body=None, *, binding=None, owner_proof=False):
    import re

    if not enabled():
        raise HTTPException(503, "Централізований Billing вимкнено")
    url = os.getenv("WAREHOUSE_BILLING_API_URL", "").rstrip("/")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise HTTPException(503, "Адреса фінансового сервісу не налаштована")
    raw = json.dumps(body, separators=(",", ":")).encode() if body is not None else b""
    payload = dict(
        principal_id=who.actor_id,
        account_id=binding.billing_account_id if binding else None,
        method=method,
        path=path,
        body_sha256=hashlib.sha256(raw).hexdigest(),
    )
    if owner_proof:
        payload.update(
            owner_verified=True,
            workspace_id=who.workspace_account_id,
            product="warehouse",
        )
    proof = transport("warehouse", "billing-api", "billing.session").sign(payload)
    try:
        with httpx.Client(
            timeout=httpx.Timeout(12, connect=3), follow_redirects=False
        ) as client:
            with client.stream(
                method,
                url + path,
                content=raw if body is not None else None,
                headers={
                    "Authorization": "Bearer " + proof,
                    "X-CarPot-Peer": "warehouse",
                    "Content-Type": "application/json",
                },
            ) as response:
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 200000:
                        raise ValueError("Response too large")
                if response.status_code != 200:
                    status = (
                        response.status_code
                        if response.status_code in (400, 401, 403, 409, 429, 503)
                        else 502
                    )
                    raise HTTPException(
                        status,
                        "Оплату не підтверджено. Перевірте стан або повторіть спробу.",
                    )
                return json.loads(data)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            503,
            "Фінансовий сервіс тимчасово недоступний. Збережений запит можна повторити.",
        ) from None


def bind(db, who):
    from . import entitlements as e

    e.owner(who)
    e.lock(db, who.workspace_account_id)
    old = db.get(EntitlementWorkspace, who.workspace_account_id, populate_existing=True)
    if old and (old.source_environment != environment() or not old.global_binding_id):
        raise HTTPException(
            409, "Існуюча фінансова прив’язка потребує погодженої міграції"
        )
    value = request(
        who,
        "POST",
        "/v1/bindings",
        dict(
            workspace_id=who.workspace_account_id,
            product="warehouse",
            account_id=old.billing_account_id if old else None,
        ),
        binding=old,
        owner_proof=True,
    )
    if (
        value.get("environment") != environment()
        or value.get("workspace_id") != who.workspace_account_id
    ):
        raise HTTPException(409, "Фінансову прив’язку не підтверджено")
    if old:
        if (
            old.billing_account_id != value["account_id"]
            or old.global_binding_id != value["binding_id"]
        ):
            raise HTTPException(409, "Конфлікт фінансової прив’язки")
        return old
    mode = os.getenv("WAREHOUSE_GLOBAL_BILLING_MODE", "dry_run")
    if mode not in {"compatibility", "dry_run", "enforce"}:
        raise HTTPException(503, "Некоректний режим пілота")
    p = EntitlementWorkspace(
        workspace_id=who.workspace_account_id,
        owner_id=who.actor_id,
        billing_account_id=value["account_id"],
        global_binding_id=value["binding_id"],
        source_environment=environment(),
        mode=mode,
        version=0,
        intervals=[],
        trial_used=False,
    )
    db.add(p)
    db.flush()
    return p


def binding(db, who):
    from . import entitlements as e

    e.owner(who)
    p = db.get(EntitlementWorkspace, who.workspace_account_id, populate_existing=True)
    if not p or p.source_environment != environment() or not p.global_binding_id:
        raise HTTPException(409, "Спершу підтвердьте підключення компанії до оплати")
    return p


def apply(db, proof):
    from . import entitlements as e

    try:
        envelope = transport("billing-api", "warehouse", "entitlements.write").verify(
            proof
        )
    except ValueError:
        raise HTTPException(403, "Некоректний фінансовий підпис") from None
    p = envelope.get("payload")
    required = {
        "schema_version",
        "event_id",
        "environment",
        "activates_real_services",
        "billing_account_id",
        "workspace_id",
        "product",
        "subscription_id",
        "version",
        "intervals",
        "trial_used",
    }
    if (
        not isinstance(p, dict)
        or set(p) != required
        or p["schema_version"] != 2
        or p["environment"] != environment()
        or p["product"] != "warehouse"
        or type(p["activates_real_services"]) is not bool
        or p["activates_real_services"] != (environment() == "production")
    ):
        raise HTTPException(422, "Некоректне середовище прав доступу")
    if (
        type(p["version"]) is not int
        or p["version"] < 1
        or type(p["trial_used"]) is not bool
        or any(
            not isinstance(p[k], str) or not 1 <= len(p[k]) <= 80
            for k in (
                "event_id",
                "workspace_id",
                "billing_account_id",
                "subscription_id",
            )
        )
    ):
        raise HTTPException(422, "Некоректні ідентифікатори прав")
    normalized = []
    if not isinstance(p["intervals"], list):
        raise HTTPException(422, "Некоректні права")
    for interval in p["intervals"]:
        if (
            not isinstance(interval, dict)
            or set(interval)
            != {
                "kind",
                "plan",
                "sku",
                "plan_version",
                "effective_from",
                "effective_until",
                "vehicle_capacity",
                "employee_seats",
            }
            or type(interval["plan_version"]) is not int
            or interval["plan_version"] < 1
            or not isinstance(interval["sku"], str)
        ):
            raise HTTPException(422, "Некоректна версія тарифу")
        expected = (
            ("warehouse." + interval["plan"])
            if interval["kind"] in ("base", "trial")
            else None
        )
        if (
            expected
            and interval["sku"] != expected
            or not expected
            and interval["sku"]
            not in {"warehouse.slots.1", "warehouse.slots.5", "warehouse.slots.10"}
        ):
            raise HTTPException(422, "Невідомий фінансовий SKU")
        normalized.append(
            {k: v for k, v in interval.items() if k not in ("sku", "plan_version")}
        )
    e.validate_intervals(normalized)
    e.lock(db, p["workspace_id"])
    local = db.get(EntitlementWorkspace, p["workspace_id"], populate_existing=True)
    if (
        not local
        or local.source_environment != p["environment"]
        or local.billing_account_id != p["billing_account_id"]
        or not local.global_binding_id
    ):
        raise HTTPException(403, "Чужа фінансова компанія")
    digest = hashlib.sha256(
        json.dumps(p, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    old = db.get(EntitlementReceipt, p["event_id"])
    if old and old.digest != digest:
        raise HTTPException(409, "Конфлікт події прав")
    if not old:
        db.add(
            EntitlementReceipt(
                id=p["event_id"], workspace_id=local.workspace_id, digest=digest
            )
        )
    if local.version == p["version"] and (
        local.intervals != normalized or local.trial_used and not p["trial_used"]
    ):
        raise HTTPException(409, "Конфлікт версії прав")
    if local.version < p["version"]:
        local.version = p["version"]
        local.intervals = normalized
        local.trial_used = local.trial_used or p["trial_used"]
    db.commit()  # acknowledgment only after committed projection+receipt
    ack = transport("warehouse", "billing-api", "entitlements.ack").sign(
        dict(
            event_id=p["event_id"],
            workspace_id=local.workspace_id,
            billing_account_id=local.billing_account_id,
            version=local.version,
        )
    )
    return {"ack": ack, "version": local.version}


def sync(db, who, p=None):
    p = p or binding(db, who)
    result = request(who, "GET", "/v1/entitlements/" + p.global_binding_id, binding=p)
    if result.get("proof"):
        ack = apply(db, result["proof"])
        request(who, "POST", "/v1/entitlements/ack", {"proof": ack["ack"]}, binding=p)
    from .entitlements import report

    return report(db, who.workspace_account_id)
