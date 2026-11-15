"""Platform staff BFF. All company reads enforce scope before serialization."""

import base64
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, cast, delete, func, select, tuple_
from sqlalchemy.exc import SQLAlchemyError
from . import security as sec
from .config import cipher, enabled, environment, get_db, origin
from .models import (
    Audit,
    Company,
    Grant,
    Note,
    SourceLink,
    SourceState,
    Staff,
    Task,
    now,
)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=6)


class NoteInput(Input):
    text: str = Field(min_length=1, max_length=4000)


class Assign(Input):
    staff_id: str = Field(min_length=1, max_length=36)


class StaffUpdate(Input):
    role: str = Field(pattern="^(Owner|Administrator|Manager|Support)$")
    active: bool
    finance: bool = False
    reason: str = Field(min_length=3, max_length=300)


class TaskInput(Input):
    next_action: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    status: str = Field(default="open", pattern="^(open|in_progress|done)$")


def staff_view(staff):
    return dict(
        id=staff.id,
        username=staff.username,
        role=staff.role,
        active=staff.active,
        can_finance=sec.finance_access(staff),
        can_assign=sec.global_access(staff),
    )


def freshness(row):
    if not row:
        return dict(
            state="unavailable", reason="source_not_synchronized", coverage="incomplete"
        )
    return dict(
        state="stale"
        if row.last_error
        or not row.last_success
        or row.last_success < now() - timedelta(minutes=15)
        else "fresh",
        environment=row.environment,
        schema_version=row.schema_version,
        watermark=row.watermark,
        fetched_at=row.fetched_at,
        last_success=row.last_success,
        last_error=row.last_error,
        coverage=row.coverage,
    )


def mask_email(value):
    name, _, domain = value.partition("@")
    return (name[:1] + "***@" + domain) if domain else "***"


def company_view(row, staff, detail=False):
    snapshot = row.snapshot
    allowed = {
        "mode",
        "status",
        "plan",
        "period_end",
        "cutoff",
        "vehicle_capacity",
        "employee_seats",
        "paid",
        "trial_used",
        "continuous_paid_until",
    }
    access = {k: v for k, v in snapshot.get("access", {}).items() if k in allowed}
    value = dict(
        id=row.id,
        display_name=row.display_name,
        environment=row.environment,
        workspace_id=row.workspace_id,
        registered_at=row.registered_at,
        manager_id=row.manager_id,
        fetched_at=row.fetched_at,
        labels=row.labels,
        state="stale" if row.fetched_at < now() - timedelta(minutes=15) else "fresh",
        access=access,
        access_incomplete=snapshot.get("access_incomplete", True),
        usage=snapshot.get("usage"),
        business_activity_at=snapshot.get("business_activity_at"),
        business_activity_coverage=snapshot.get("business_activity_coverage"),
    )
    # Binding ownership references are not financial amounts, still hidden from Support.
    if staff.role != "Support":
        value["binding"] = snapshot.get("binding")
    if detail:
        value["people"] = [
            {**p, "email": mask_email(p.get("email", ""))}
            for p in snapshot.get("people", [])
        ]
    return value


def create_app():
    app = FastAPI(
        title="CarPot Control Center", docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.middleware("http")
    async def guard(request, call_next):
        if not enabled():
            return JSONResponse({"detail": "Not found"}, status_code=404)
        try:
            expected_origin = origin()
        except (ValueError, RuntimeError, KeyError):
            return JSONResponse(
                {"detail": "Control Center потребує налаштування"}, status_code=503
            )
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.headers.get("origin") != expected_origin
        ):
            return JSONResponse({"detail": "Недійсне джерело запиту"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 16000:
                    return JSONResponse({"detail": "Запит завеликий"}, status_code=413)
            request._body = bytes(raw)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"detail": "Перевірте формат полів"}, status_code=422)

    @app.exception_handler(RuntimeError)
    @app.exception_handler(KeyError)
    @app.exception_handler(SQLAlchemyError)
    async def db_error(request, exc):
        return JSONResponse(
            {"detail": "Control Center тимчасово недоступний"}, status_code=503
        )

    @app.get("/status")
    def status():
        return dict(enabled=True, environment=environment())

    @app.post("/auth/login")
    def login(data: Login, request: Request, response: Response, db=Depends(get_db)):
        staff, token, csrf = sec.login(
            db,
            data.username,
            data.password,
            data.code,
            request.client.host if request.client else "unknown",
        )
        response.set_cookie(
            sec.COOKIE,
            token,
            max_age=14400,
            path=sec.COOKIE_PATH,
            secure=environment() != "local",
            httponly=True,
            samesite="strict",
        )
        return dict(staff=staff_view(staff), csrf=csrf)

    @app.get("/auth/me")
    def me(staff=Depends(sec.identity)):
        return staff_view(staff)

    @app.post("/auth/logout", status_code=204)
    def logout(
        request: Request,
        response: Response,
        staff=Depends(sec.identity),
        db=Depends(get_db),
    ):
        db.delete(request.state.control_session)
        sec.audit(db, staff.id, "auth.logout", "staff", "session")
        db.commit()
        response.delete_cookie(
            sec.COOKIE,
            path=sec.COOKIE_PATH,
            secure=environment() != "local",
            httponly=True,
            samesite="strict",
        )

    @app.get("/readiness")
    def readiness(staff=Depends(sec.identity), db=Depends(get_db)):
        cipher()  # detect missing/invalid key without disclosing it
        db.scalar(select(Staff.id).limit(1))
        return dict(
            staff_schema="001",
            source=freshness(db.get(SourceState, "warehouse:" + environment())),
            environment=environment(),
        )

    @app.get("/staff")
    def staff_list(staff=Depends(sec.identity), db=Depends(get_db)):
        if not sec.global_access(staff):
            raise HTTPException(403, "Немає дозволу")
        return [
            staff_view(s)
            for s in db.scalars(select(Staff).order_by(Staff.username).limit(100))
        ]

    @app.patch("/staff/{staff_id}")
    def update_staff(
        staff_id: str,
        data: StaffUpdate,
        staff=Depends(sec.identity),
        db=Depends(get_db),
    ):
        if staff.role != "Owner":
            raise HTTPException(403, "Лише Owner")
        if staff_id == staff.id:
            raise HTTPException(
                409, "Власний привілейований доступ змінює інший Owner або оператор"
            )
        target = db.get(Staff, staff_id, with_for_update=True)
        if not target:
            raise HTTPException(404)
        before = dict(role=target.role, active=target.active, finance=target.finance)
        target.role, target.active, target.finance = (
            data.role,
            data.active,
            data.finance if data.role != "Support" else False,
        )
        sec.revoke(db, target.id)
        sec.audit(
            db,
            staff.id,
            "staff.update",
            "staff",
            target.id,
            reason=data.reason,
            diff=dict(
                before=before,
                after=dict(
                    role=target.role, active=target.active, finance=target.finance
                ),
            ),
        )
        db.commit()
        return staff_view(target)

    @app.get("/companies")
    def listing(
        q: str = Query("", max_length=120),
        cursor: str | None = Query(None, max_length=1000),
        limit: int = Query(30, ge=1, le=100),
        plan: str = Query("", max_length=30),
        status: str = Query("", max_length=30),
        linking: str = Query("", pattern="^(|linked|unlinked|conflict)$"),
        manager: str = Query("", max_length=36),
        since: datetime | None = None,
        registered_from: date | None = None,
        sort: str = Query("name", pattern="^(name|registered)$"),
        staff=Depends(sec.identity),
        db=Depends(get_db),
    ):
        query = select(Company).where(
            Company.environment == environment(), sec.scope_query(staff)
        )
        if q.strip():
            # Escape wildcard metacharacters; searchable only within staff scope.
            clean = (
                q.strip()
                .lower()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            query = query.where(
                Company.search_text.like("%" + clean + "%", escape="\\")
            )
        if plan:
            query = query.where(Company.snapshot["access"]["plan"].as_string() == plan)
        if status:
            query = query.where(
                Company.snapshot["access"]["status"].as_string() == status
            )
        if manager:
            query = query.where(Company.manager_id == manager)
        if registered_from:
            query = query.where(
                Company.registered_at
                >= datetime.combine(registered_from, time.min, ZoneInfo("Europe/Kyiv"))
            )
        if since:
            if since.tzinfo is None:
                raise HTTPException(422, "Дата має містити timezone")
            query = query.where(Company.registered_at >= since)
        linked = select(SourceLink.company_id).where(
            SourceLink.system == "billing", SourceLink.status == "verified"
        )
        if linking == "linked":
            query = query.where(Company.id.in_(linked))
        elif linking == "unlinked":
            query = query.where(
                ~Company.id.in_(
                    select(SourceLink.company_id).where(
                        SourceLink.system == "billing",
                        SourceLink.status.in_(["verified", "conflict"]),
                    )
                )
            )
        elif linking == "conflict":
            query = query.where(
                Company.id.in_(
                    select(SourceLink.company_id).where(SourceLink.status == "conflict")
                )
            )
        order = Company.display_name if sort == "name" else Company.registered_at
        # Cursor includes all filters to prevent accidental mixing of views.
        filters = [
            q,
            plan,
            status,
            linking,
            manager,
            since.isoformat() if since else None,
            registered_from.isoformat() if registered_from else None,
            sort,
        ]
        if cursor:
            try:
                data = json.loads(base64.urlsafe_b64decode(cursor))
                if data["filters"] != filters:
                    raise ValueError()
                value = (
                    data["value"]
                    if sort == "name"
                    else datetime.fromisoformat(data["value"])
                )
                query = query.where(
                    tuple_(order, Company.id) > tuple_(value, data["id"])
                )
            except (ValueError, TypeError, KeyError):
                raise HTTPException(422, "Недійсний cursor") from None
        rows = list(db.scalars(query.order_by(order, Company.id).limit(limit + 1)))
        more, rows = len(rows) > limit, rows[:limit]
        next_cursor = None
        if more:
            last = rows[-1]
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(
                    dict(
                        filters=filters,
                        value=last.display_name
                        if sort == "name"
                        else last.registered_at.isoformat(),
                        id=last.id,
                    )
                ).encode()
            ).decode()
        links = list(
            db.scalars(
                select(SourceLink).where(
                    SourceLink.company_id.in_([r.id for r in rows]),
                    SourceLink.system == "billing",
                )
            )
        )
        link_status = {link.company_id: link.status for link in links}
        items = [
            dict(
                **company_view(row, staff), linking=link_status.get(row.id, "unlinked")
            )
            for row in rows
        ]
        return dict(
            items=items,
            next_cursor=next_cursor,
            source=freshness(db.get(SourceState, "warehouse:" + environment())),
        )

    @app.get("/overview")
    def overview(staff=Depends(sec.identity), db=Depends(get_db)):
        base = (Company.environment == environment(), sec.scope_query(staff))
        total = db.scalar(select(func.count()).select_from(Company).where(*base))
        linked_ids = select(SourceLink.company_id).where(
            SourceLink.system == "billing", SourceLink.status == "verified"
        )
        linked_count = db.scalar(
            select(func.count())
            .select_from(Company)
            .where(*base, Company.id.in_(linked_ids))
        )
        access_status = Company.snapshot["access"]["status"].as_string()
        rows = db.execute(
            select(access_status, func.count()).where(*base).group_by(access_status)
        ).all()
        paid_until = cast(
            Company.snapshot["access"]["continuous_paid_until"].as_string(),
            DateTime(timezone=True),
        )
        expiring = db.scalar(
            select(func.count())
            .select_from(Company)
            .where(*base, paid_until >= now(), paid_until <= now() + timedelta(days=14))
        )
        conflicts = db.scalar(
            select(func.count())
            .select_from(Company)
            .where(
                *base,
                Company.id.in_(
                    select(SourceLink.company_id).where(SourceLink.status == "conflict")
                ),
            )
        )
        source = freshness(db.get(SourceState, "warehouse:" + environment()))
        return dict(
            expiring_14d=expiring if source["state"] != "unavailable" else None,
            conflicts=conflicts if source["state"] != "unavailable" else None,
            workspaces=total if source["state"] != "unavailable" else None,
            linked=linked_count if source["state"] != "unavailable" else None,
            states=dict(rows),
            source=source,
            environment=environment(),
            metrics=dict(
                mrr={"state": "unavailable", "reason": "metric_policy_not_approved"},
                cash_collected={
                    "state": "unavailable",
                    "reason": "no_complete_financial_projection",
                },
                churn={"state": "unavailable", "reason": "metric_policy_not_approved"},
            ),
        )

    @app.get("/companies/{company_id}")
    def detail(company_id: str, staff=Depends(sec.identity), db=Depends(get_db)):
        row = sec.company(db, staff, company_id)
        value = company_view(row, staff, True)
        links = list(
            db.scalars(select(SourceLink).where(SourceLink.company_id == row.id))
        )
        value["links"] = [
            dict(
                system=l.system,
                environment=l.environment,
                status=l.status,
                evidence=l.evidence,
                verified_by=l.verified_by,
                verified_at=l.verified_at,
                entity_type=l.entity_type,
                source_id=l.source_id if staff.role != "Support" else None,
            )
            for l in links
        ]
        return value

    @app.get("/companies/{company_id}/finance")
    def finance(company_id: str, staff=Depends(sec.identity), db=Depends(get_db)):
        row = sec.company(db, staff, company_id)
        if not sec.finance_access(staff):
            raise HTTPException(403, "Фінансові суми недоступні")
        from .finance import read_finance

        return read_finance(db, row)

    @app.get("/companies/{company_id}/notes")
    def notes(company_id: str, staff=Depends(sec.identity), db=Depends(get_db)):
        sec.company(db, staff, company_id)
        return [
            dict(id=n.id, text=n.text, staff_id=n.staff_id, created_at=n.created_at)
            for n in db.scalars(
                select(Note)
                .where(Note.company_id == company_id)
                .order_by(Note.created_at.desc(), Note.id)
                .limit(50)
            )
        ]

    @app.post("/companies/{company_id}/notes", status_code=201)
    def note(
        company_id: str,
        data: NoteInput,
        staff=Depends(sec.identity),
        db=Depends(get_db),
    ):
        sec.company(db, staff, company_id)
        if not data.text.strip():
            raise HTTPException(422)
        row = Note(company_id=company_id, staff_id=staff.id, text=data.text.strip())
        db.add(row)
        db.flush()
        # Body deliberately absent from audit; mutation and metadata audit atomic.
        sec.audit(
            db, staff.id, "notes.write", company_id, row.id, diff={"created": True}
        )
        db.commit()
        return dict(id=row.id)

    @app.post("/companies/{company_id}/assign")
    def assign(
        company_id: str, data: Assign, staff=Depends(sec.identity), db=Depends(get_db)
    ):
        row = sec.company(db, staff, company_id)
        if not sec.global_access(staff):
            raise HTTPException(403)
        target = db.get(Staff, data.staff_id)
        if not target or not target.active:
            raise HTTPException(422)
        # Assignment grants company context; replacing a manager revokes old scope.
        old_manager = row.manager_id
        if target.role != "Support":
            if old_manager:
                db.execute(
                    delete(Grant).where(
                        Grant.company_id == row.id, Grant.staff_id == old_manager
                    )
                )
            row.manager_id = target.id
        if not db.get(Grant, (row.id, target.id)):
            db.add(Grant(company_id=row.id, staff_id=target.id))
        sec.audit(
            db,
            staff.id,
            "assignments.write",
            row.id,
            row.id,
            diff=dict(staff_id=target.id),
        )
        db.commit()
        return {"assigned": True}

    @app.get("/tasks")
    def tasks(staff=Depends(sec.identity), db=Depends(get_db)):
        allowed = select(Company.id).where(
            Company.environment == environment(), sec.scope_query(staff)
        )
        query = (
            select(Task, Company.display_name, Staff.username)
            .join(Company, Company.id == Task.company_id)
            .join(Staff, Staff.id == Task.assignee_id)
            .where(Task.company_id.in_(allowed))
        )
        if not sec.global_access(staff):
            query = query.where(Task.assignee_id == staff.id)
        return [
            dict(
                id=t.id,
                company_id=t.company_id,
                assignee_id=t.assignee_id,
                next_action=t.next_action,
                status=t.status,
                due_at=t.due_at,
                company_name=company_name,
                assignee_name=assignee_name,
            )
            for t, company_name, assignee_name in db.execute(
                query.order_by(Task.created_at.desc(), Task.id).limit(100)
            )
        ]

    @app.post("/companies/{company_id}/tasks", status_code=201)
    def task(
        company_id: str,
        data: TaskInput,
        staff=Depends(sec.identity),
        db=Depends(get_db),
    ):
        sec.company(db, staff, company_id)
        if data.due_at and data.due_at.tzinfo is None:
            raise HTTPException(422, "Дата має містити timezone")
        row = Task(
            company_id=company_id,
            assignee_id=staff.id,
            next_action=data.next_action.strip(),
            status=data.status,
            due_at=data.due_at,
        )
        if not row.next_action:
            raise HTTPException(422)
        db.add(row)
        db.flush()
        sec.audit(
            db, staff.id, "tasks.write", company_id, row.id, diff={"created": True}
        )
        db.commit()
        return {"id": row.id}

    @app.patch("/tasks/{task_id}")
    def update_task(
        task_id: str, data: TaskInput, staff=Depends(sec.identity), db=Depends(get_db)
    ):
        row = db.get(Task, task_id, with_for_update=True)
        if not row:
            raise HTTPException(404)
        sec.company(db, staff, row.company_id)
        if not sec.global_access(staff) and row.assignee_id != staff.id:
            raise HTTPException(404)
        if not data.next_action.strip() or data.due_at and data.due_at.tzinfo is None:
            raise HTTPException(422)
        row.next_action, row.status, row.due_at = (
            data.next_action.strip(),
            data.status,
            data.due_at,
        )
        sec.audit(
            db,
            staff.id,
            "tasks.write",
            row.company_id,
            row.id,
            diff={"status": row.status},
        )
        db.commit()
        return {"updated": True}

    @app.get("/audit")
    def audit_list(staff=Depends(sec.identity), db=Depends(get_db)):
        if staff.role != "Owner":
            raise HTTPException(403)
        return [
            dict(
                actor=a.actor,
                permission=a.permission,
                scope=a.scope,
                target=a.target,
                request_id=a.request_id,
                safe_diff=a.safe_diff,
                result=a.result,
                occurred_at=a.occurred_at,
            )
            for a in db.scalars(
                select(Audit).order_by(Audit.occurred_at.desc(), Audit.id).limit(100)
            )
        ]

    return app
