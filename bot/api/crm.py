import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext

from bot.database.repositories.crm_admin_repo import (
    ALLOWED_ADMIN_ROLES,
    create_admin_user,
    get_admin_user,
    list_admin_users,
    set_admin_password,
    set_admin_user_active,
    update_admin_user_role,
)
from bot.database.repositories.crm_audit_repo import list_admin_audit_logs
from bot.database.repositories.lead_repo import (
    ALLOWED_STATUSES,
    list_site_leads,
    update_site_lead_status,
)
from bot.database.repositories.crm_payment_repo import list_crm_payments
from bot.database.repositories.crm_user_repo import (
    get_crm_seller_cars,
    get_crm_seller_detail,
    get_crm_seller_services,
    get_crm_seller_site,
    get_crm_seller_subscriptions,
    list_crm_sellers,
)
from bot.database.repositories.crm_repo import (
    create_admin_session_by_admin_id,
    get_admin_by_id,
    get_admin_by_username,
    get_session_by_token,
    log_admin_action,
    mark_session_used,
)

router = APIRouter(prefix="/admin/crm")
templates = Jinja2Templates(directory="bot/api/templates")
CRM_COOKIE_NAME = "crm_session"
CRM_VIEW_ROLES = {"super_admin", "admin", "manager"}
CRM_AUDIT_ROLES = {"super_admin", "admin"}
CRM_PASSWORD_SESSION_DAYS = 7
CRM_ADMIN_PASSWORD_MIN_LENGTH = 8
CRM_ADMIN_PASSWORD_BCRYPT_MAX_BYTES = 72
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def require_roles(admin, allowed_roles):
    if admin["role"] not in allowed_roles:
        raise HTTPException(status_code=403, detail="CRM access denied")


def can_manage_admins(admin):
    return admin["role"] == "super_admin"


def can_view_audit_logs(admin):
    return admin["role"] in CRM_AUDIT_ROLES


def can_update_leads(admin):
    return admin["role"] in CRM_VIEW_ROLES


def _is_expired(expires_at) -> bool:
    return expires_at <= datetime.utcnow()


def _request_ip(request: Request):
    if request.client:
        return request.client.host
    return None


def _require_crm_view_role(admin):
    require_roles(admin, CRM_VIEW_ROLES)


def _template_context(request: Request, admin=None, **kwargs):
    context = {
        "request": request,
        "admin": admin,
        "can_view_audit": can_view_audit_logs(admin) if admin else False,
        "can_manage_admins": can_manage_admins(admin) if admin else False,
    }
    context.update(kwargs)
    return context


def _parse_is_active(value: str):
    return value in {"1", "true", "True", "yes", "on", "active"}


async def get_current_admin(request: Request):
    token = request.cookies.get(CRM_COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=401, detail="CRM session required")

    session = await get_session_by_token(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid CRM session")

    if _is_expired(session["expires_at"]):
        raise HTTPException(status_code=401, detail="CRM session expired")

    if session["used_at"] is None:
        raise HTTPException(status_code=401, detail="CRM session is not activated")

    admin = await get_admin_by_id(session["admin_user_id"])

    if not admin:
        raise HTTPException(status_code=401, detail="Admin user not found")

    if not admin["is_active"]:
        raise HTTPException(status_code=403, detail="Admin user is inactive")

    return admin


async def _render_crm_admins(
    request: Request,
    admin,
    *,
    error: str | None = None,
    success: str | None = None,
    status_code: int = 200,
):
    admin_users = await list_admin_users()

    return templates.TemplateResponse(
        "admin/crm_admins.html",
        _template_context(
            request,
            admin,
            admin_users=admin_users,
            allowed_roles=sorted(ALLOWED_ADMIN_ROLES),
            error=error,
            success=success,
        ),
        status_code=status_code,
    )


async def _crm_magic_token_login(request: Request, token: str):
    session = await get_session_by_token(token)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid CRM login token")

    if _is_expired(session["expires_at"]):
        raise HTTPException(status_code=401, detail="CRM login token expired")

    if session["used_at"] is not None:
        raise HTTPException(status_code=401, detail="CRM login token already used")

    session = await mark_session_used(token)
    admin = await get_admin_by_id(session["admin_user_id"])

    if not admin:
        raise HTTPException(status_code=401, detail="Admin user not found")

    if not admin["is_active"]:
        raise HTTPException(status_code=403, detail="Admin user is inactive")

    await log_admin_action(
        admin["id"],
        "crm_login",
        entity_type="admin_session",
        entity_id=str(session["id"]),
        ip=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    max_age = max(0, int((session["expires_at"] - datetime.utcnow()).total_seconds()))
    response = RedirectResponse(url="/admin/crm", status_code=303)
    response.set_cookie(
        CRM_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.get("/login")
async def crm_login_page(request: Request, token: str | None = None):
    if token:
        return await _crm_magic_token_login(request, token)

    return templates.TemplateResponse(
        "admin/crm_login.html",
        _template_context(request, title="CRM Login"),
    )


@router.post("/login")
async def crm_password_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    login_error = "Невірний логін або пароль"
    username = username.strip()
    admin = await get_admin_by_username(username) if username else None

    if not admin or not admin["is_active"]:
        return templates.TemplateResponse(
            "admin/crm_login.html",
            _template_context(request, title="CRM Login", error=login_error, username=username),
            status_code=401,
        )

    if not admin["password_hash"]:
        return templates.TemplateResponse(
            "admin/crm_login.html",
            _template_context(
                request,
                title="CRM Login",
                error="Password is not configured",
                username=username,
            ),
            status_code=401,
        )

    if not verify_password(password, admin["password_hash"]):
        return templates.TemplateResponse(
            "admin/crm_login.html",
            _template_context(request, title="CRM Login", error=login_error, username=username),
            status_code=401,
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=CRM_PASSWORD_SESSION_DAYS)
    session = await create_admin_session_by_admin_id(
        admin["id"],
        token,
        expires_at,
        used=True,
    )

    await log_admin_action(
        admin["id"],
        "crm_password_login",
        entity_type="admin_session",
        entity_id=str(session["id"]),
        ip=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    response = RedirectResponse(url="/admin/crm", status_code=303)
    response.set_cookie(
        CRM_COOKIE_NAME,
        token,
        max_age=CRM_PASSWORD_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.get("")
async def crm_dashboard(request: Request):
    admin = await get_current_admin(request)
    _require_crm_view_role(admin)

    cards = [
        {
            "title": "Leads",
            "text": "Manage site requests",
            "url": "/admin/crm/leads",
        },
        {
            "title": "Users",
            "text": "View sellers and user profiles",
            "url": "/admin/crm/users",
        },
        {
            "title": "Payments",
            "text": "Review payment records",
            "url": "/admin/crm/payments",
        },
    ]

    if can_view_audit_logs(admin):
        cards.append(
            {
                "title": "Audit",
                "text": "Review CRM audit logs",
                "url": "/admin/crm/audit",
            }
        )

    if can_manage_admins(admin):
        cards.append(
            {
                "title": "Admins",
                "text": "Manage CRM administrators",
                "url": "/admin/crm/admins",
            }
        )

    return templates.TemplateResponse(
        "admin/crm_dashboard.html",
        _template_context(
            request,
            admin,
            cards=cards,
        ),
    )


@router.get("/leads")
async def crm_leads(request: Request, status: str | None = None):
    admin = await get_current_admin(request)
    _require_crm_view_role(admin)

    if status == "":
        status = None

    if status is not None and status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid lead status")

    leads = await list_site_leads(status=status)

    return templates.TemplateResponse(
        "admin/crm_leads.html",
        _template_context(
            request,
            admin,
            leads=leads,
            current_status=status,
            allowed_statuses=["new", "in_progress", "done", "rejected"],
        ),
    )


@router.post("/leads/{lead_id}/status")
async def crm_update_lead_status(
    request: Request,
    lead_id: int,
    status: str = Form(...),
):
    admin = await get_current_admin(request)
    if not can_update_leads(admin):
        raise HTTPException(status_code=403, detail="Lead status update denied")

    if status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid lead status")

    lead = await update_site_lead_status(
        lead_id=lead_id,
        status=status,
        manager_admin_id=admin["id"],
    )

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    await log_admin_action(
        admin["id"],
        "lead_status_changed",
        entity_type="site_lead",
        entity_id=str(lead_id),
        payload={"status": status},
        ip=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return RedirectResponse(url="/admin/crm/leads", status_code=303)


@router.get("/users")
async def crm_users(
    request: Request,
    q: str | None = None,
    verified: str | None = None,
    has_site: str | None = None,
):
    admin = await get_current_admin(request)
    _require_crm_view_role(admin)

    q = q.strip() if q else None

    if verified == "":
        verified = None

    if has_site == "":
        has_site = None

    if verified is not None and verified not in {"yes", "no"}:
        raise HTTPException(status_code=400, detail="Invalid verified filter")

    if has_site is not None and has_site not in {"yes", "no"}:
        raise HTTPException(status_code=400, detail="Invalid site filter")

    sellers = await list_crm_sellers(
        query=q,
        verified=verified,
        has_site=has_site,
    )

    return templates.TemplateResponse(
        "admin/crm_users.html",
        _template_context(
            request,
            admin,
            sellers=sellers,
            q=q or "",
            verified=verified,
            has_site=has_site,
        ),
    )


@router.get("/sellers/{seller_id}")
async def crm_seller_detail(request: Request, seller_id: int):
    admin = await get_current_admin(request)
    _require_crm_view_role(admin)

    seller = await get_crm_seller_detail(seller_id)

    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")

    cars = await get_crm_seller_cars(seller_id)
    services = await get_crm_seller_services(seller_id)
    site = await get_crm_seller_site(seller_id)
    subscriptions = await get_crm_seller_subscriptions(seller_id)

    return templates.TemplateResponse(
        "admin/crm_seller_detail.html",
        _template_context(
            request,
            admin,
            seller=seller,
            cars=cars,
            services=services,
            site=site,
            subscriptions=subscriptions,
        ),
    )


@router.get("/payments")
async def crm_payments(
    request: Request,
    status: str | None = None,
    product: str | None = None,
    seller_id: int | None = None,
):
    admin = await get_current_admin(request)
    _require_crm_view_role(admin)

    if status == "":
        status = None

    if product == "":
        product = None

    payments = await list_crm_payments(
        status=status,
        product=product,
        seller_id=seller_id,
    )

    return templates.TemplateResponse(
        "admin/crm_payments.html",
        _template_context(
            request,
            admin,
            payments=payments,
            status=status or "",
            product=product or "",
            seller_id=seller_id or "",
        ),
    )


@router.get("/audit")
async def crm_audit(
    request: Request,
    action: str | None = None,
    actor_admin_id: int | None = None,
):
    admin = await get_current_admin(request)
    require_roles(admin, CRM_AUDIT_ROLES)

    if action == "":
        action = None

    logs = await list_admin_audit_logs(
        action=action,
        actor_admin_id=actor_admin_id,
    )

    return templates.TemplateResponse(
        "admin/crm_audit.html",
        _template_context(
            request,
            admin,
            logs=logs,
            action=action or "",
            actor_admin_id=actor_admin_id or "",
        ),
    )


@router.get("/admins")
async def crm_admins(request: Request):
    admin = await get_current_admin(request)
    require_roles(admin, {"super_admin"})

    return await _render_crm_admins(request, admin)


@router.post("/admins/create")
async def crm_create_admin(
    request: Request,
    telegram_id: int = Form(...),
    username: str | None = Form(None),
    role: str = Form(...),
):
    admin = await get_current_admin(request)
    require_roles(admin, {"super_admin"})

    if role not in ALLOWED_ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="Invalid admin role")

    username = username.strip() if username else None
    new_admin = await create_admin_user(telegram_id, username, role)

    if not new_admin:
        raise HTTPException(status_code=400, detail="Admin telegram_id already exists")

    await log_admin_action(
        admin["id"],
        "admin_user_created",
        entity_type="admin_user",
        entity_id=str(new_admin["id"]),
        payload={"telegram_id": telegram_id, "username": username, "role": role},
        ip=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return RedirectResponse(url="/admin/crm/admins", status_code=303)


@router.post("/admins/{admin_id}/role")
async def crm_update_admin_role(
    request: Request,
    admin_id: int,
    role: str = Form(...),
):
    admin = await get_current_admin(request)
    require_roles(admin, {"super_admin"})

    if role not in ALLOWED_ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="Invalid admin role")

    updated_admin = await update_admin_user_role(admin_id, role)

    if not updated_admin:
        raise HTTPException(status_code=404, detail="Admin user not found")

    await log_admin_action(
        admin["id"],
        "admin_user_role_updated",
        entity_type="admin_user",
        entity_id=str(admin_id),
        payload={"role": role},
        ip=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return RedirectResponse(url="/admin/crm/admins", status_code=303)


@router.post("/admins/{admin_id}/password")
async def crm_set_admin_password(
    request: Request,
    admin_id: int,
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    admin = await get_current_admin(request)
    require_roles(admin, {"super_admin"})

    target_admin = await get_admin_user(admin_id)
    if not target_admin:
        raise HTTPException(status_code=404, detail="Admin user not found")

    if not password:
        return await _render_crm_admins(
            request,
            admin,
            error="Password is required",
            status_code=400,
        )

    if password != password_confirm:
        return await _render_crm_admins(
            request,
            admin,
            error="Password confirmation does not match",
            status_code=400,
        )

    if len(password) < CRM_ADMIN_PASSWORD_MIN_LENGTH:
        return await _render_crm_admins(
            request,
            admin,
            error=f"Password must be at least {CRM_ADMIN_PASSWORD_MIN_LENGTH} characters",
            status_code=400,
        )

    if len(password.encode("utf-8")) > CRM_ADMIN_PASSWORD_BCRYPT_MAX_BYTES:
        return await _render_crm_admins(
            request,
            admin,
            error="Password must be 72 bytes or less",
            status_code=400,
        )

    password_hash = hash_password(password)
    updated_admin = await set_admin_password(admin_id, password_hash)

    if not updated_admin:
        raise HTTPException(status_code=404, detail="Admin user not found")

    await log_admin_action(
        admin["id"],
        "admin_password_updated",
        entity_type="admin_user",
        entity_id=str(admin_id),
        payload={"target_admin_id": admin_id},
        ip=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return RedirectResponse(url="/admin/crm/admins", status_code=303)


@router.post("/admins/{admin_id}/active")
async def crm_update_admin_active(
    request: Request,
    admin_id: int,
    is_active: str = Form(...),
):
    admin = await get_current_admin(request)
    require_roles(admin, {"super_admin"})

    next_is_active = _parse_is_active(is_active)

    if admin_id == admin["id"] and not next_is_active:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    updated_admin = await set_admin_user_active(admin_id, next_is_active)

    if not updated_admin:
        raise HTTPException(status_code=404, detail="Admin user not found")

    await log_admin_action(
        admin["id"],
        "admin_user_active_updated",
        entity_type="admin_user",
        entity_id=str(admin_id),
        payload={"is_active": next_is_active},
        ip=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return RedirectResponse(url="/admin/crm/admins", status_code=303)


@router.get("/logout")
async def crm_logout(request: Request):
    try:
        admin = await get_current_admin(request)
        await log_admin_action(
            admin["id"],
            "crm_logout",
            ip=_request_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except HTTPException:
        pass

    response = RedirectResponse(url="/admin/crm/logged-out", status_code=303)
    response.delete_cookie(
        CRM_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.get("/logged-out")
async def crm_logged_out(request: Request):
    return templates.TemplateResponse(
        "admin/crm_base.html",
        _template_context(
            request,
            title="CRM Logged Out",
            content_title="Logged out",
            content_text="CRM session cleared.",
        ),
    )
