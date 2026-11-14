"""Workspace product policy, local-test opt-in only; never a financial ledger."""

from datetime import datetime, timedelta
import hashlib, json, os
from fastapi import HTTPException
from sqlalchemy import select, event, inspect
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.engine import make_url
from app.config import database_url
from app.models import Account, Vehicle, Part, Order, now, uid
from app.models.entitlements import (
    EntitlementWorkspace,
    EntitlementReceipt,
    DonorProvenance,
)

PLANS = {
    "standard": {"amount_minor": 100000, "vehicle_capacity": 10, "employee_seats": 5},
    "premium": {"amount_minor": 450000, "vehicle_capacity": 50, "employee_seats": 10},
}
PACKS = {"pack_1": (30000, 1), "pack_5": (120000, 5), "pack_10": (200000, 10)}


def enabled():
    if os.getenv("WAREHOUSE_ENTITLEMENTS_ENABLED") != "true":
        return False
    url = make_url(database_url())
    return url.host in ("localhost", "127.0.0.1", "::1") and (
        url.database or ""
    ).endswith("_test")


def lock(db, workspace):
    return db.scalar(
        select(Account)
        .where(Account.id == workspace)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )


def projection(db, workspace):
    return (
        db.get(EntitlementWorkspace, workspace, populate_existing=True)
        if enabled()
        else None
    )


def enforced(db, workspace):
    row = projection(db, workspace)
    return bool(row and row.mode == "enforce")


def validate_intervals(intervals):
    if not isinstance(intervals, list) or len(intervals) > 1000:
        raise HTTPException(422, "Некоректні права")
    bases = []
    for i in intervals:
        if not isinstance(i, dict) or set(i) != {
            "kind",
            "plan",
            "effective_from",
            "effective_until",
            "vehicle_capacity",
            "employee_seats",
        }:
            raise HTTPException(422, "Некоректний часовий контракт")
        if i["kind"] not in ("base", "trial", "addon") or i["plan"] not in PLANS:
            raise HTTPException(422, "Невідомий тариф")
        if any(
            type(i[k]) is not int or i[k] < 0
            for k in ("vehicle_capacity", "employee_seats")
        ):
            raise HTTPException(422, "Некоректний ліміт")
        if i["kind"] != "addon" and any(
            i[k] != PLANS[i["plan"]][k] for k in ("vehicle_capacity", "employee_seats")
        ):
            raise HTTPException(422, "Ліміти не відповідають тарифу")
        if i["kind"] == "addon" and (
            i["employee_seats"] != 0 or not 1 <= i["vehicle_capacity"] <= 1000
        ):
            raise HTTPException(422, "Некоректний пакет")
        try:
            a, b = (
                datetime.fromisoformat(i[k])
                for k in ("effective_from", "effective_until")
            )
            if a.tzinfo is None or b.tzinfo is None or b <= a:
                raise ValueError()
        except (TypeError, ValueError):
            raise HTTPException(422, "Некоректний період") from None
        if i["kind"] != "addon":
            bases.append((a, b))
    bases.sort()
    if any(a[1] > b[0] for a, b in zip(bases, bases[1:])):
        raise HTTPException(422, "Періоди тарифів перетинаються")


def state(db, workspace, *, at=None):
    at = at or now()
    p = projection(db, workspace)
    result = dict(
        mode=p.mode if p else "compatibility",
        status="FREE",
        plan=None,
        period_end=None,
        cutoff=None,
        vehicle_capacity=0,
        employee_seats=0,
        paid=False,
        trial_used=bool(p and p.trial_used),
    )
    if not p:
        return result
    bases = [i for i in p.intervals if i["kind"] != "addon"]
    active = [
        i
        for i in bases
        if datetime.fromisoformat(i["effective_from"])
        <= at
        < datetime.fromisoformat(i["effective_until"])
    ]
    chosen = active[0] if active else None
    if chosen:
        result.update(
            status="TRIAL" if chosen["kind"] == "trial" else "ACTIVE", paid=True
        )
    else:
        past = [i for i in bases if datetime.fromisoformat(i["effective_until"]) <= at]
        last = (
            max(past, key=lambda i: datetime.fromisoformat(i["effective_until"]))
            if past
            else None
        )
        if last:
            end = datetime.fromisoformat(last["effective_until"])
            result.update(status="EXPIRED", cutoff=end, period_end=end)
            if last["kind"] == "base" and at < end + timedelta(hours=72):
                chosen = last
                result.update(
                    status="GRACE", paid=True, cutoff=end + timedelta(hours=72)
                )
    if chosen:
        end = datetime.fromisoformat(chosen["effective_until"])
        result.update(
            plan=chosen["plan"],
            period_end=end,
            vehicle_capacity=chosen["vehicle_capacity"],
            employee_seats=chosen["employee_seats"],
            cutoff=end if chosen["kind"] == "trial" else end + timedelta(hours=72),
        )
        result["vehicle_capacity"] += sum(
            i["vehicle_capacity"]
            for i in p.intervals
            if i["kind"] == "addon"
            and datetime.fromisoformat(i["effective_from"])
            <= at
            < datetime.fromisoformat(i["effective_until"])
        )
    return result


def usage(db, workspace):
    # Read committed scalar values after the workspace lock, rather than cached
    # ORM entities loaded before a concurrent restore/receipt/reactivation.
    # Overlay our pending writes explicitly: populate_existing would erase them.
    with db.no_autoflush:
        vehicles = dict(
            db.execute(
                select(Vehicle.id, Vehicle.archived).where(
                    Vehicle.account_id == workspace
                )
            ).all()
        )
        parts = {
            r.id: (r.vehicle_id, r.quantity, r.reserved_quantity)
            for r in db.execute(
                select(
                    Part.id, Part.vehicle_id, Part.quantity, Part.reserved_quantity
                ).where(Part.account_id == workspace)
            )
        }
        origins = (
            dict(
                db.execute(
                    select(DonorProvenance.part_id, DonorProvenance.vehicle_id).where(
                        DonorProvenance.workspace_id == workspace
                    )
                ).all()
            )
            if enabled()
            else {}
        )
        employees = dict(
            db.execute(
                select(Account.id, Account.is_active).where(
                    Account.workspace_account_id == workspace
                )
            ).all()
        )
        for row in list(db.new) + list(db.dirty):
            if isinstance(row, Vehicle) and row.account_id == workspace:
                vehicles[row.id or id(row)] = row.archived
            if isinstance(row, Part) and row.account_id == workspace:
                parts[row.id or id(row)] = (
                    row.vehicle_id,
                    row.quantity,
                    row.reserved_quantity,
                )
            if isinstance(row, Account) and row.workspace_account_id == workspace:
                employees[row.id or id(row)] = row.is_active
        occupied = {key for key, archived in vehicles.items() if not archived}
        for key, (donor, quantity, reserved) in parts.items():
            if (quantity or 0) > 0 or (reserved or 0) > 0:
                occupied.update(v for v in (donor, origins.get(key)) if v is not None)
        return dict(
            vehicles=len(occupied),
            employees=sum(active is not False for active in employees.values()),
        )


def report(db, workspace):
    s = state(db, workspace)
    u = usage(db, workspace)
    return {
        **s,
        "usage": u,
        "over_limit": {
            "vehicles": u["vehicles"] > s["vehicle_capacity"],
            "employees": u["employees"] > s["employee_seats"],
        },
        "would_block": (
            ["vehicle.create", "stock.receipt", "order.create", "dismantle"]
            if not s["paid"]
            else []
        )
        + (
            ["vehicle.create", "vehicle.restore"]
            if u["vehicles"] >= s["vehicle_capacity"]
            else []
        )
        + (
            ["team.create", "team.reactivate"]
            if u["employees"] >= s["employee_seats"]
            else []
        ),
        "compatibility": not enabled() or s["mode"] != "enforce",
        "checkout_available": False,
    }


def configure_workspace(db, workspace, mode):
    """Explicit local pilot enrollment; never called by registration or a client route."""
    if not enabled() or mode not in ("compatibility", "dry_run", "enforce"):
        raise HTTPException(503, "Потрібний окремий локальний пілот")
    lock(db, workspace)
    p = projection(db, workspace)
    if not p:
        raise HTTPException(409, "Спершу потрібне підтвердження власника")
    for part in db.scalars(
        select(Part).where(Part.account_id == workspace, Part.vehicle_id.is_not(None))
    ):
        if not db.get(DonorProvenance, part.id):
            db.add(
                DonorProvenance(
                    part_id=part.id, workspace_id=workspace, vehicle_id=part.vehicle_id
                )
            )
    p.mode = mode
    return report(db, workspace)


def require_paid(db, workspace):
    if enforced(db, workspace) and not state(db, workspace)["paid"]:
        raise HTTPException(
            402,
            "Підписка завершена. Доступні перегляд, експорт та завершення старих зобов’язань.",
        )


def policy(db, who, method, path, body, path_params):
    """Explicit operation policy, after RBAC and before domain execution."""
    workspace = who.workspace_account_id
    if not enforced(db, workspace):
        return
    if (
        method in ("GET", "HEAD", "OPTIONS")
        or path.startswith("/api/v1/billing/")
        or path.startswith("/api/v1/auth/")
    ):
        return
    if path.startswith("/api/v1/team/") and (
        body.get("is_active") is False or path.endswith("/reset-password")
    ):
        return
    if (
        path.endswith(("/categories/recover", "/articles/recover"))
        or path == "/api/v1/pricing/guidance"
    ):
        return
    s = state(db, workspace)
    if s["paid"]:
        return
    if path.endswith("/operations") and body.get("type") == "release":
        return
    if path.startswith("/api/v1/orders/"):
        action = path_params.get("action")
        safe = action in ("release", "cancel", "sell", "reserve") or path.endswith(
            ("/complete", "/status")
        )
        if safe:
            order = db.scalar(
                select(Order).where(
                    Order.id == path_params.get("id"), Order.account_id == workspace
                )
            )
            if order and s["cutoff"] and order.created_at < s["cutoff"]:
                return
    raise HTTPException(
        402, "Ця нова операція потребує активної підписки. Дані збережено."
    )


@event.listens_for(DBSession, "before_flush")
def quota_guard(db, context, instances):
    if not enabled() or db.info.get("entitlement_guard"):
        return
    db.info["entitlement_guard"] = True
    try:
        candidates = list(db.new) + list(db.dirty) + list(db.deleted)
        scopes = {
            r.account_id for r in candidates if isinstance(r, (Vehicle, Part, Order))
        }
        scopes.update(
            r.workspace_account_id
            for r in candidates
            if isinstance(r, Account) and r.workspace_account_id
        )
        for workspace in sorted(scopes):
            with db.no_autoflush:
                if not enforced(db, workspace):
                    continue
                lock(db, workspace)
                s = state(db, workspace)
                growing_vehicle = False
                growing_team = False
                for row in candidates:
                    if row in db.deleted and isinstance(row, (Part, Vehicle)):
                        raise HTTPException(
                            409, "Фізичне видалення складської історії заборонено"
                        )
                    if (
                        isinstance(row, Order)
                        and row in db.new
                        and row.account_id == workspace
                        and not s["paid"]
                    ):
                        raise HTTPException(402, "Нове замовлення потребує підписки")
                    if isinstance(row, Vehicle) and row.account_id == workspace:
                        hist = inspect(row).attrs.archived.history
                        growth = row in db.new or bool(
                            hist.deleted and hist.deleted[0] and not row.archived
                        )
                        growing_vehicle |= growth
                        if growth and not s["paid"]:
                            raise HTTPException(
                                402, "Новий автомобіль потребує підписки"
                            )
                        if row.archived:
                            blockers = list(
                                db.scalars(
                                    select(Part).where(
                                        Part.account_id == workspace,
                                        Part.vehicle_id == row.id,
                                    )
                                )
                            )
                            if any(
                                (p.quantity or 0) > 0 or (p.reserved_quantity or 0) > 0
                                for p in blockers
                            ):
                                raise HTTPException(
                                    409,
                                    "Місце не звільнено: донор має фізичні залишки або резерви. Продайте або документовано спишіть їх.",
                                )
                    if (
                        isinstance(row, Account)
                        and row.workspace_account_id == workspace
                    ):
                        h = inspect(row).attrs.is_active.history
                        growth = row in db.new or bool(
                            h.deleted and not h.deleted[0] and row.is_active
                        )
                        growing_team |= growth
                        if growth and not s["paid"]:
                            raise HTTPException(
                                402, "Новий працівник потребує підписки"
                            )
                    if isinstance(row, Part) and row.account_id == workspace:
                        quantities = inspect(row).attrs.quantity.history
                        increases = row in db.new or bool(
                            quantities.deleted
                            and (row.quantity or 0) > quantities.deleted[0]
                        )
                        if (
                            increases
                            and not s["paid"]
                            and not db.info.get("verified_entitlement_return")
                        ):
                            raise HTTPException(402, "Нове приймання потребує підписки")
                        if (
                            increases
                            and row.vehicle_id
                            and (row.quantity or 0) > 0
                            and not db.info.get("verified_entitlement_return")
                        ):
                            donor = db.get(Vehicle, row.vehicle_id)
                            if donor and donor.archived:
                                growing_vehicle = True
                        old = db.get(DonorProvenance, row.id) if row.id else None
                        h = inspect(row).attrs.vehicle_id.history
                        origin = (
                            old.vehicle_id
                            if old
                            else (h.deleted[0] if h.deleted else row.vehicle_id)
                        )
                        if origin and row.vehicle_id != origin:
                            raise HTTPException(
                                409,
                                "Походження деталі не можна видалити або змінити для звільнення місця",
                            )
                        if origin and not old:
                            if not row.id:
                                row.id = uid()
                            db.add(
                                DonorProvenance(
                                    part_id=row.id,
                                    workspace_id=workspace,
                                    vehicle_id=origin,
                                )
                            )
                u = usage(db, workspace)
                if growing_vehicle and u["vehicles"] > s["vehicle_capacity"]:
                    raise HTTPException(409, "Досягнуто місткість гаража")
                if growing_team and u["employees"] > s["employee_seats"]:
                    raise HTTPException(409, "Досягнуто ліміт працівників")
    finally:
        db.info.pop("entitlement_guard", None)


def local_bridge():
    if not enabled():
        raise HTTPException(503, "Ізольований entitlement-контур вимкнено")
    from bot.billing.db import Database
    from bot.billing.warehouse import WarehouseBridge, migrate_phase2

    key = os.getenv("WAREHOUSE_ENTITLEMENT_TEST_KEY", "").encode()
    dsn = os.getenv("CARPOT_BILLING_TEST_DSN", "")
    if len(key) < 32 or not dsn:
        raise HTTPException(503, "Локальний Billing transport не налаштовано")
    db = Database(dsn, enabled=True)
    db.migrate()
    migrate_phase2(db)
    return WarehouseBridge(db, key)


def owner(who):
    if who.user.role != "DIRECTOR" or who.actor_id != who.workspace_account_id:
        raise HTTPException(403, "Дія доступна підтвердженому власнику")


def bind_owner(db, who):
    owner(who)
    bridge = local_bridge()
    lock(db, who.workspace_account_id)
    p = db.get(EntitlementWorkspace, who.workspace_account_id)
    token = bridge.owner_transport.sign(
        dict(workspace_id=who.workspace_account_id, owner_id=who.actor_id)
    )
    account = bridge.bind(token)
    if p:
        if p.billing_account_id != account or p.owner_id != who.actor_id:
            raise HTTPException(409, "Canonical binding потребує перевірки власника")
        return p
    p = EntitlementWorkspace(
        workspace_id=who.workspace_account_id,
        billing_account_id=account,
        owner_id=who.actor_id,
        mode="compatibility",
        version=0,
        intervals=[],
        trial_used=False,
    )
    db.add(p)
    db.flush()
    return p


def accept(db, token):
    bridge = local_bridge()
    e = bridge.entitlement_transport.verify(token)
    p = e["payload"]
    required = {
        "schema_version",
        "environment",
        "event_id",
        "workspace_id",
        "billing_account_id",
        "version",
        "intervals",
        "trial_used",
    }
    if (
        not isinstance(p, dict)
        or set(p) != required
        or type(p.get("trial_used")) is not bool
    ):
        raise HTTPException(422, "Некоректний snapshot envelope")
    if any(
        not isinstance(p[k], str) or not 1 <= len(p[k]) <= 80
        for k in ("event_id", "workspace_id", "billing_account_id")
    ):
        raise HTTPException(422, "Некоректний ідентифікатор")
    if p.get("schema_version") != 2 or p.get("environment") != "test":
        raise HTTPException(422, "Непідтримувана версія")
    validate_intervals(p.get("intervals"))
    if type(p.get("version")) is not int or p["version"] < 1:
        raise HTTPException(422, "Некоректна версія")
    lock(db, p["workspace_id"])
    binding = db.get(EntitlementWorkspace, p["workspace_id"], populate_existing=True)
    if not binding or binding.billing_account_id != p["billing_account_id"]:
        raise HTTPException(403, "Чужий workspace")
    digest = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
    event_id = p["event_id"]
    old = db.get(EntitlementReceipt, event_id)
    # Transport jti is consumed even when envelope carries a previously seen event.
    if db.get(EntitlementReceipt, e["jti"]):
        raise HTTPException(409, "Transport replay")
    db.add(
        EntitlementReceipt(
            id=e["jti"], workspace_id=binding.workspace_id, digest=digest
        )
    )
    if old:
        if old.digest != digest:
            raise HTTPException(409, "Конфлікт події")
        return "duplicate"
    db.add(
        EntitlementReceipt(
            id=event_id, workspace_id=binding.workspace_id, digest=digest
        )
    )
    if binding.version >= p["version"]:
        if binding.version == p["version"] and binding.intervals != p["intervals"]:
            raise HTTPException(409, "Конфлікт версії")
        return "stale"
    binding.version = p["version"]
    binding.intervals = p["intervals"]
    binding.trial_used = binding.trial_used or bool(p.get("trial_used"))
    return "applied"
