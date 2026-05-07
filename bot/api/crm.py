from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.database.repositories.lead_repo import (
    ALLOWED_STATUSES,
    list_site_leads,
    update_site_lead_status,
)
from bot.database.repositories.crm_repo import (
    get_admin_by_id,
    get_session_by_token,
    log_admin_action,
    mark_session_used,
)

router = APIRouter(prefix="/admin/crm")
templates = Jinja2Templates(directory="bot/api/templates")
CRM_COOKIE_NAME = "crm_session"


def _is_expired(expires_at) -> bool:
    return expires_at <= datetime.utcnow()


def _request_ip(request: Request):
    if request.client:
        return request.client.host
    return None


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


@router.get("/login")
async def crm_login(request: Request, token: str):
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


@router.get("")
async def crm_dashboard(request: Request):
    admin = await get_current_admin(request)

    return templates.TemplateResponse(
        "admin/crm_dashboard.html",
        {
            "request": request,
            "admin": admin,
            "cards": [
                {
                    "title": "Leads",
                    "text": "Manage site requests",
                    "url": "/admin/crm/leads",
                },
                {"title": "Users", "text": "Coming soon", "url": None},
                {"title": "Payments", "text": "Coming soon", "url": None},
                {"title": "Logs", "text": "Coming soon", "url": None},
            ],
        },
    )


@router.get("/leads")
async def crm_leads(request: Request, status: str | None = None):
    admin = await get_current_admin(request)

    if status == "":
        status = None

    if status is not None and status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid lead status")

    leads = await list_site_leads(status=status)

    return templates.TemplateResponse(
        "admin/crm_leads.html",
        {
            "request": request,
            "admin": admin,
            "leads": leads,
            "current_status": status,
            "allowed_statuses": ["new", "in_progress", "done", "rejected"],
        },
    )


@router.post("/leads/{lead_id}/status")
async def crm_update_lead_status(
    request: Request,
    lead_id: int,
    status: str = Form(...),
):
    admin = await get_current_admin(request)

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
        {
            "request": request,
            "title": "CRM Logged Out",
            "content_title": "Logged out",
            "content_text": "CRM session cleared.",
        },
    )
