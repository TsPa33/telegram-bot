import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.database.repositories.seller_crm_repo import (
    create_crm_session,
    delete_crm_session,
    get_active_crm_subscription,
    get_crm_account_by_slug,
    get_crm_account_for_login,
    get_crm_session,
    get_seller_crm_dashboard,
    list_seller_crm_cars,
    list_seller_crm_leads,
    list_seller_crm_services,
    list_seller_crm_sources,
)
from bot.services.seller_crm import SELLER_CRM_SESSION_DAYS, verify_crm_password

router = APIRouter(prefix="/crm/seller")
templates = Jinja2Templates(directory="bot/api/templates")
SELLER_CRM_COOKIE = "seller_crm_session"


def _seller_crm_context(request: Request, **kwargs):
    context = {"request": request, "title": "Seller CRM"}
    context.update(kwargs)
    return context


def _is_expired(expires_at) -> bool:
    return expires_at <= datetime.utcnow()


async def _current_session(request: Request):
    token = request.cookies.get(SELLER_CRM_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Seller CRM session required")

    session = await get_crm_session(token)
    if not session or _is_expired(session["expires_at"]):
        raise HTTPException(status_code=401, detail="Seller CRM session expired")
    if not session["is_active"] or not session["crm_enabled"]:
        raise HTTPException(status_code=403, detail="Seller CRM account disabled")

    subscription = await get_active_crm_subscription(session["seller_id"])
    if not subscription:
        raise HTTPException(status_code=402, detail="Seller CRM subscription expired")
    return session, subscription


@router.get("/demo")
async def seller_crm_demo(request: Request):
    demo_stats = {
        "visits_today": 186,
        "leads_today": 14,
        "telegram_clicks_today": 42,
        "active_listings": 38,
        "conversion": 7.5,
        "new_leads": 6,
        "in_progress_leads": 5,
        "closed_leads": 31,
        "page_views_today": 514,
        "cta_clicks_today": 73,
        "listing_views": 8240,
        "listing_clicks": 391,
        "services_count": 8,
        "service_views": 1190,
        "service_requests": 64,
    }
    demo_leads = [
        {"name": "Олександр", "phone": "+380••• •• 42", "status": "new", "source": "telegram", "message": "Цікавить BMW X5"},
        {"name": "Марина", "phone": "+380••• •• 18", "status": "in_progress", "source": "google", "message": "Запис на діагностику"},
        {"name": "СТО Партнер", "phone": "+380••• •• 77", "status": "done", "source": "site", "message": "Підбір запчастин"},
    ]
    return templates.TemplateResponse(
        "seller_crm/dashboard.html",
        _seller_crm_context(
            request,
            title="Демо CRM CarPot",
            demo_mode=True,
            account={"crm_slug": "demo", "shop_name": "Demo Auto Hub"},
            subscription={"expires_at": datetime.utcnow() + timedelta(days=30)},
            stats=demo_stats,
            leads=demo_leads,
            cars=[],
            services=[],
            sources=[{"source": "telegram", "visits": 93}, {"source": "google", "visits": 71}, {"source": "direct", "visits": 22}],
        ),
    )


@router.get("/login")
async def seller_crm_login_page(request: Request, slug: str | None = None):
    return templates.TemplateResponse(
        "seller_crm/login.html",
        _seller_crm_context(request, slug=slug),
    )


@router.post("/login")
async def seller_crm_login(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(...),
    slug: str | None = Form(None),
):
    account = await get_crm_account_for_login(identifier, slug)
    login_error = "Невірний логін або пароль"

    if not account or not account["is_active"] or not account["crm_enabled"]:
        return templates.TemplateResponse(
            "seller_crm/login.html",
            _seller_crm_context(request, error=login_error, identifier=identifier, slug=slug),
            status_code=401,
        )

    subscription = await get_active_crm_subscription(account["seller_id"])
    if not subscription:
        return templates.TemplateResponse(
            "seller_crm/login.html",
            _seller_crm_context(request, error="CRM підписка завершилась. Продовжіть її в Telegram.", identifier=identifier, slug=slug),
            status_code=402,
        )

    if not verify_crm_password(password, account["password_hash"]):
        return templates.TemplateResponse(
            "seller_crm/login.html",
            _seller_crm_context(request, error=login_error, identifier=identifier, slug=slug),
            status_code=401,
        )

    token = secrets.token_urlsafe(32)
    await create_crm_session(account["id"], token, datetime.utcnow() + timedelta(days=SELLER_CRM_SESSION_DAYS))

    response = RedirectResponse(url=f"/crm/seller/{account['crm_slug']}", status_code=303)
    response.set_cookie(
        SELLER_CRM_COOKIE,
        token,
        max_age=SELLER_CRM_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def seller_crm_logout(request: Request):
    token = request.cookies.get(SELLER_CRM_COOKIE)
    if token:
        await delete_crm_session(token)
    response = RedirectResponse(url="/crm/seller/login", status_code=303)
    response.delete_cookie(SELLER_CRM_COOKIE)
    return response


@router.get("/{crm_slug}")
async def seller_crm_dashboard(request: Request, crm_slug: str):
    account = await get_crm_account_by_slug(crm_slug)
    if not account:
        raise HTTPException(status_code=404, detail="CRM account not found")

    try:
        session, subscription = await _current_session(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse(url=f"/crm/seller/login?slug={crm_slug}", status_code=303)
        raise

    if session["seller_id"] != account["seller_id"] or session["crm_slug"] != crm_slug:
        raise HTTPException(status_code=403, detail="Forbidden")

    seller_id = account["seller_id"]
    stats = await get_seller_crm_dashboard(seller_id)
    leads = await list_seller_crm_leads(seller_id)
    cars = await list_seller_crm_cars(seller_id)
    services = await list_seller_crm_services(seller_id)
    sources = await list_seller_crm_sources(seller_id)

    return templates.TemplateResponse(
        "seller_crm/dashboard.html",
        _seller_crm_context(
            request,
            title="Професійна CRM CarPot",
            demo_mode=False,
            account=account,
            subscription=subscription,
            stats=stats or {},
            leads=leads,
            cars=cars,
            services=services,
            sources=sources,
        ),
    )
