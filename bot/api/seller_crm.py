import os
import secrets
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.database.repositories.car_repo import (
    create_seller_car,
    delete_seller_car,
    get_cars_by_seller,
    update_seller_car_description,
    update_seller_car_photo,
)
from bot.database.repositories.model_repo import get_brands_with_ids, get_model_id, get_models_by_brand_id
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
from bot.database.repositories.service_repo import (
    create_service,
    delete_service_by_seller,
    get_service_by_seller,
    get_services_by_seller,
    update_service_field,
)
from bot.database.repositories.site_repo import (
    get_site_by_seller,
    publish_site,
    replace_site_config_draft,
    update_site_config_draft,
)
from bot.services.domain_service import build_site_url
from bot.services.seller_crm import SELLER_CRM_SESSION_DAYS, verify_crm_password
from bot.services.site_config import get_theme_presets, merge_with_default
from bot.services.storage import upload_image

router = APIRouter(prefix="/crm/seller")
templates = Jinja2Templates(directory="bot/api/templates")
SELLER_CRM_COOKIE = "seller_crm_session"

MODULE_KEYS = [
    ("hero", "Hero"),
    ("services", "Послуги"),
    ("cars", "Авто"),
    ("gallery", "Галерея"),
    ("works", "Наші роботи"),
    ("pricing", "Ціни"),
    ("contacts", "Контакти"),
    ("map", "Карта"),
    ("cta", "Callback / CTA"),
    ("reviews", "Відгуки"),
    ("footer", "Footer"),
]


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


async def _authorized_account(request: Request, crm_slug: str):
    account = await get_crm_account_by_slug(crm_slug)
    if not account:
        raise HTTPException(status_code=404, detail="CRM account not found")

    try:
        session, subscription = await _current_session(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise HTTPException(
                status_code=303,
                detail=f"/crm/seller/login?slug={crm_slug}",
            ) from exc
        raise

    if session["seller_id"] != account["seller_id"] or session["crm_slug"] != crm_slug:
        raise HTTPException(status_code=403, detail="Forbidden")

    return account, subscription


def _redirect(crm_slug: str, section: str = "website", status: str = "saved"):
    return RedirectResponse(
        url=f"/crm/seller/{crm_slug}/website?section={section}&status={status}",
        status_code=303,
    )


def _as_config(site) -> dict[str, Any]:
    raw = site.get("config_draft") or site.get("config_live") or {}
    return merge_with_default(raw if isinstance(raw, dict) else {})


def _split_lines(value: str | None) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


async def _upload_to_cloudinary(file: UploadFile | None) -> str | None:
    if not file or not file.filename:
        return None

    suffix = Path(file.filename).suffix or ".jpg"
    fd, temp_path = tempfile.mkstemp(prefix="carpot-crm-", suffix=suffix)
    os.close(fd)
    try:
        content = await file.read()
        if not content:
            return None
        Path(temp_path).write_bytes(content)
        return await upload_image(temp_path)
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass


def _list_item(title: str, description: str = "", image: str | None = None, **extra) -> dict[str, Any]:
    item = {"title": title.strip(), "description": (description or "").strip()}
    if image:
        item["image"] = image
    item.update({k: v for k, v in extra.items() if v not in (None, "")})
    return item


def _collect_media(config: dict[str, Any], services, cars) -> list[dict[str, str]]:
    media: list[dict[str, str]] = []
    logo = config.get("header", {}).get("logo")
    if logo:
        media.append({"type": "Лого", "url": logo, "title": "Header logo"})
    for url in config.get("hero", {}).get("banners", []):
        media.append({"type": "Банер", "url": url, "title": "Hero banner"})
    for image in config.get("gallery", {}).get("images", []):
        url = image.get("url") if isinstance(image, dict) else image
        if url:
            media.append({"type": "Галерея", "url": url, "title": image.get("title", "Gallery") if isinstance(image, dict) else "Gallery"})
    for work in config.get("works", {}).get("items", []):
        if isinstance(work, dict) and work.get("image"):
            media.append({"type": "Робота", "url": work["image"], "title": work.get("title") or "Work"})
    for service in services:
        if service.get("photo_id"):
            media.append({"type": "Послуга", "url": service["photo_id"], "title": service.get("title") or "Service"})
    for car in cars:
        if car.get("photo_id"):
            media.append({"type": "Авто", "url": car["photo_id"], "title": f"{car.get('brand', '')} {car.get('model', '')}".strip()})
    return media


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
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

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


@router.get("/{crm_slug}/website")
async def seller_crm_website(request: Request, crm_slug: str, section: str = "website", status: str | None = None):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    site = await get_site_by_seller(seller_id)
    if not site:
        raise HTTPException(status_code=404, detail="Seller site is not created yet")

    config = _as_config(site)
    services = [dict(row) for row in await get_services_by_seller(seller_id)]
    cars = [dict(row) for row in await get_cars_by_seller(seller_id)]
    brands = await get_brands_with_ids()
    selected_brand = brands[0]["id"] if brands else None
    models = await get_models_by_brand_id(selected_brand) if selected_brand else []
    live_url = build_site_url(site["subdomain"])
    media = _collect_media(config, services, cars)

    return templates.TemplateResponse(
        "seller_crm/website.html",
        _seller_crm_context(
            request,
            title="Медіа та дизайн — Seller CRM",
            account=account,
            subscription=subscription,
            site=site,
            config=config,
            services=services,
            cars=cars,
            brands=brands,
            models=models,
            media=media,
            live_url=live_url,
            section=section,
            status=status,
            themes=get_theme_presets(),
            module_keys=MODULE_KEYS,
        ),
    )


@router.post("/{crm_slug}/website/texts")
async def update_website_texts(
    request: Request,
    crm_slug: str,
    header_title: str = Form(""),
    hero_title: str = Form(""),
    hero_subtitle: str = Form(""),
    phones: str = Form(""),
    address: str = Form(""),
    telegram: str = Form(""),
    whatsapp: str = Form(""),
    viber: str = Form(""),
    instagram: str = Form(""),
    facebook: str = Form(""),
    map_embed: str = Form(""),
    footer_text: str = Form(""),
    cta_title: str = Form(""),
    cta_text: str = Form(""),
    seo_title: str = Form(""),
    seo_description: str = Form(""),
):
    account, _ = await _authorized_account(request, crm_slug)
    await update_site_config_draft(
        account["seller_id"],
        {
            "header": {"title": header_title.strip(), "seo_title": seo_title.strip(), "seo_description": seo_description.strip()},
            "hero": {"title": hero_title.strip(), "subtitle": hero_subtitle.strip()},
            "contacts": {
                "phones": _split_lines(phones),
                "address": address.strip(),
                "map_embed": map_embed.strip(),
                "messengers": {"telegram": telegram.strip(), "whatsapp": whatsapp.strip(), "viber": viber.strip()},
                "socials": {"instagram": instagram.strip(), "facebook": facebook.strip()},
            },
            "cta": {"title": cta_title.strip(), "text": cta_text.strip()},
            "footer": {"text": footer_text.strip()},
        },
    )
    return _redirect(crm_slug, "website")


@router.post("/{crm_slug}/website/logo")
async def update_logo(request: Request, crm_slug: str, logo: UploadFile | None = File(None), remove: str | None = Form(None)):
    account, _ = await _authorized_account(request, crm_slug)
    url = None if remove else await _upload_to_cloudinary(logo)
    if remove or url:
        await update_site_config_draft(account["seller_id"], {"header": {"logo": url}})
    return _redirect(crm_slug, "logo")


@router.post("/{crm_slug}/website/theme")
async def update_theme(request: Request, crm_slug: str, theme: str = Form("default")):
    account, _ = await _authorized_account(request, crm_slug)
    presets = get_theme_presets()
    preset = presets.get(theme, presets["default"])
    await update_site_config_draft(account["seller_id"], {"theme": {"scheme": preset["scheme"], "preset": theme, "accent": preset["accent"]}})
    return _redirect(crm_slug, "theme")


@router.post("/{crm_slug}/website/modules")
async def update_modules(request: Request, crm_slug: str):
    account, _ = await _authorized_account(request, crm_slug)
    form = await request.form()
    modules = {key: key in form for key, _ in MODULE_KEYS}
    modules["products"] = "products" in form
    await update_site_config_draft(account["seller_id"], {"modules": modules})
    return _redirect(crm_slug, "modules")


@router.post("/{crm_slug}/website/banners/add")
async def add_banner(request: Request, crm_slug: str, banner: UploadFile | None = File(None), url: str = Form("")):
    account, _ = await _authorized_account(request, crm_slug)
    site = await get_site_by_seller(account["seller_id"])
    config = _as_config(site)
    image_url = await _upload_to_cloudinary(banner) or url.strip()
    if image_url:
        config.setdefault("hero", {}).setdefault("banners", []).append(image_url)
        await replace_site_config_draft(account["seller_id"], config)
    return _redirect(crm_slug, "banners")


@router.post("/{crm_slug}/website/banners/update")
async def update_banners(request: Request, crm_slug: str, banners: str = Form("")):
    account, _ = await _authorized_account(request, crm_slug)
    await update_site_config_draft(account["seller_id"], {"hero": {"banners": _split_lines(banners)}})
    return _redirect(crm_slug, "banners")


@router.post("/{crm_slug}/website/gallery/add")
async def add_gallery_item(
    request: Request,
    crm_slug: str,
    title: str = Form(""),
    description: str = Form(""),
    image: UploadFile | None = File(None),
    url: str = Form(""),
):
    account, _ = await _authorized_account(request, crm_slug)
    site = await get_site_by_seller(account["seller_id"])
    config = _as_config(site)
    image_url = await _upload_to_cloudinary(image) or url.strip()
    if image_url:
        config.setdefault("gallery", {}).setdefault("images", []).append({"url": image_url, "title": title.strip(), "description": description.strip()})
        await replace_site_config_draft(account["seller_id"], config)
    return _redirect(crm_slug, "gallery")


@router.post("/{crm_slug}/website/gallery/update")
async def update_gallery(request: Request, crm_slug: str, images: str = Form("")):
    account, _ = await _authorized_account(request, crm_slug)
    items = [{"url": line} for line in _split_lines(images)]
    await update_site_config_draft(account["seller_id"], {"gallery": {"images": items}})
    return _redirect(crm_slug, "gallery")


@router.post("/{crm_slug}/website/prices/add")
async def add_price_item(request: Request, crm_slug: str, title: str = Form(""), price: str = Form(""), description: str = Form("")):
    account, _ = await _authorized_account(request, crm_slug)
    site = await get_site_by_seller(account["seller_id"])
    config = _as_config(site)
    if title.strip():
        config.setdefault("pricing", {}).setdefault("items", []).append(_list_item(title, description, price=price.strip()))
        await replace_site_config_draft(account["seller_id"], config)
    return _redirect(crm_slug, "prices")


@router.post("/{crm_slug}/website/prices/update")
async def update_prices(request: Request, crm_slug: str, prices: str = Form("")):
    account, _ = await _authorized_account(request, crm_slug)
    items = []
    for line in _split_lines(prices):
        parts = [part.strip() for part in line.split("|")]
        items.append(_list_item(parts[0], parts[2] if len(parts) > 2 else "", price=parts[1] if len(parts) > 1 else ""))
    await update_site_config_draft(account["seller_id"], {"pricing": {"items": items}})
    return _redirect(crm_slug, "prices")


@router.post("/{crm_slug}/website/services/save")
async def save_service(
    request: Request,
    crm_slug: str,
    service_id: int | None = Form(None),
    title: str = Form(...),
    category: str = Form("СТО"),
    city: str = Form(""),
    address: str = Form(""),
    description: str = Form(""),
    price: str = Form(""),
    website: str = Form(""),
    photo: UploadFile | None = File(None),
):
    account, _ = await _authorized_account(request, crm_slug)
    seller_id = account["seller_id"]
    image_url = await _upload_to_cloudinary(photo)
    if service_id:
        service = await get_service_by_seller(service_id, seller_id)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        for field, value in {
            "title": title,
            "category": category,
            "city": city,
            "address": address,
            "description": description,
            "price": price,
            "website": website,
        }.items():
            await update_service_field(service_id, field, value.strip())
        if image_url:
            await update_service_field(service_id, "photo_id", image_url)
    else:
        new_service_id = await create_service(seller_id, category.strip(), title.strip(), city.strip(), address.strip(), description.strip(), website.strip(), image_url)
        if new_service_id and price.strip():
            await update_service_field(new_service_id, "price", price.strip())
    return _redirect(crm_slug, "services")


@router.post("/{crm_slug}/website/services/delete")
async def delete_service_route(request: Request, crm_slug: str, service_id: int = Form(...)):
    account, _ = await _authorized_account(request, crm_slug)
    await delete_service_by_seller(service_id, account["seller_id"])
    return _redirect(crm_slug, "services")


@router.post("/{crm_slug}/website/cars/save")
async def save_car(
    request: Request,
    crm_slug: str,
    car_id: int | None = Form(None),
    brand: str = Form(""),
    model: str = Form(""),
    description: str = Form(""),
    photo: UploadFile | None = File(None),
):
    account, _ = await _authorized_account(request, crm_slug)
    seller_id = account["seller_id"]
    image_url = await _upload_to_cloudinary(photo)
    if car_id:
        ok = await update_seller_car_description(car_id, seller_id, description.strip())
        if not ok:
            raise HTTPException(status_code=404, detail="Car not found")
        if image_url:
            await update_seller_car_photo(car_id, seller_id, image_url)
    else:
        model_id = await get_model_id(brand, model)
        if not model_id:
            raise HTTPException(status_code=400, detail="Brand and model are required")
        await create_seller_car(seller_id, model_id, description.strip(), image_url)
    return _redirect(crm_slug, "cars")


@router.post("/{crm_slug}/website/cars/delete")
async def delete_car_route(request: Request, crm_slug: str, car_id: int = Form(...)):
    account, _ = await _authorized_account(request, crm_slug)
    await delete_seller_car(car_id, account["seller_id"])
    return _redirect(crm_slug, "cars")


@router.post("/{crm_slug}/website/publish")
async def publish_site_route(request: Request, crm_slug: str):
    account, _ = await _authorized_account(request, crm_slug)
    await publish_site(account["seller_id"])
    return _redirect(crm_slug, "publish", "published")


@router.get("/{crm_slug}/website/preview")
async def preview_draft_site(request: Request, crm_slug: str):
    account, _ = await _authorized_account(request, crm_slug)
    site = await get_site_by_seller(account["seller_id"])
    if not site:
        raise HTTPException(status_code=404, detail="Seller site is not created yet")
    config = _as_config(site)
    return templates.TemplateResponse(
        "site.html",
        {
            "request": request,
            "subdomain": site["subdomain"],
            "site_id": site["id"],
            "config": config,
            "seller": account,
            "cars": [dict(row) for row in await get_cars_by_seller(account["seller_id"])],
            "services": [dict(row) for row in await get_services_by_seller(account["seller_id"])],
            "products": config.get("products", {}),
        },
    )
