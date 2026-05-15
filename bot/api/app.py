import json
import logging

from aiogram import Bot
from fastapi import APIRouter, FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.api.liqpay_callback import router as liqpay_router
from bot.api.crm import router as crm_router
from bot.api.seller_crm import router as seller_crm_router
from bot.config import BOT_TOKEN

from bot.database.repositories.site_repo import get_site_by_subdomain
from bot.database.repositories.seller_repo import get_seller_by_id
from bot.database.repositories.car_repo import get_cars_by_seller
from bot.database.repositories.service_repo import get_services_by_seller
from bot.database.repositories.lead_repo import create_site_lead
from bot.database.repositories.buyer_lead_repo import create_buyer_lead
from bot.database.repositories.marketplace_repo import (
    list_featured_sellers,
    list_marketplace_cars,
    list_marketplace_services,
    marketplace_summary,
)
from bot.database.repositories.analytics_repo import (
    ALLOWED_ANALYTICS_EVENT_TYPES,
    add_event,
    upsert_session,
)

from bot.services.demo_seed_service import get_demo_render_preset
from bot.services.site_config import merge_with_default
from bot.utils.subdomain import is_valid_subdomain
from bot.services.domain_service import extract_subdomain_from_host
from bot.services.telegram_sender import send_message_to_seller

app = FastAPI()
router = APIRouter()

templates = Jinja2Templates(directory="bot/api/templates")
bot = Bot(token=BOT_TOKEN)
logger = logging.getLogger(__name__)

MARKETING_TELEGRAM_BOT_URL = "https://t.me/CarPotbot"
MARKETING_TELEGRAM_SUPPORT_URL = "https://t.me/CarPotbot"
MARKETING_SUPPORT_EMAIL = "support@carpot.com.ua"
MARKETING_SITE_URL = "https://carpot.com.ua"

MAX_ANALYTICS_PAYLOAD_BYTES = 8192
VALID_DEVICE_TYPES = {"mobile", "desktop", "tablet", "bot", "unknown"}


def _client_ip(request: Request) -> str | None:
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.split(",", 1)[0].strip()[:80]

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()[:80]

    if request.client:
        return request.client.host[:80]
    return None


def _optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _short_text(value, max_length: int = 500) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    return value[:max_length]


def _detect_client(user_agent: str | None) -> tuple[str, str, str]:
    ua = (user_agent or "").lower()

    if not ua:
        return "unknown", "unknown", "unknown"

    if any(marker in ua for marker in ("bot", "crawler", "spider", "telegrambot")):
        device_type = "bot"
    elif "ipad" in ua or "tablet" in ua:
        device_type = "tablet"
    elif "mobile" in ua or "iphone" in ua or "android" in ua:
        device_type = "mobile"
    else:
        device_type = "desktop"

    if "edg/" in ua:
        browser = "Edge"
    elif "chrome/" in ua or "crios/" in ua:
        browser = "Chrome"
    elif "safari/" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox/" in ua:
        browser = "Firefox"
    elif "telegram" in ua:
        browser = "Telegram"
    else:
        browser = "unknown"

    if "windows" in ua:
        os_name = "Windows"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        os_name = "iOS"
    elif "android" in ua:
        os_name = "Android"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "unknown"

    return device_type, browser, os_name


async def _analytics_payload(request: Request) -> dict:
    content_length = request.headers.get("content-length")
    try:
        payload_size = int(content_length or 0)
    except ValueError:
        payload_size = 0

    if payload_size > MAX_ANALYTICS_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Analytics payload too large")

    body = await request.body()

    if len(body) > MAX_ANALYTICS_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Analytics payload too large")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning(
            "Invalid analytics payload content_type=%s size=%s",
            request.headers.get("content-type"),
            len(body),
        )
        raise HTTPException(status_code=400, detail="Invalid analytics payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid analytics payload")

    return payload


def marketing_context(
    request: Request,
    title: str,
    description: str,
    path: str = "/",
) -> dict:
    return {
        "request": request,
        "page_title": title,
        "page_description": description,
        "og_url": f"{MARKETING_SITE_URL}{path}",
        "telegram_bot_url": MARKETING_TELEGRAM_BOT_URL,
        "telegram_support_url": MARKETING_TELEGRAM_SUPPORT_URL,
        "support_email": MARKETING_SUPPORT_EMAIL,
        "buyer_mode": False,
    }


def _as_text(value, max_length: int = 500) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()

    if not cleaned:
        return None

    return cleaned[:max_length]


def _boolean_filter(value: str | None) -> bool | None:
    if value in (None, "", "all"):
        return None

    return value in {"1", "true", "yes", "on", "verified"}


async def buyer_marketplace_context(
    request: Request,
    title: str,
    description: str,
    path: str,
    query: str | None = None,
    city: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    category: str | None = None,
    urgent: str | None = None,
    verified: str | None = None,
    limit: int = 12,
) -> dict:
    q = _as_text(query, 160)
    city_filter = _as_text(city, 120)
    brand_filter = _as_text(brand, 120)
    model_filter = _as_text(model, 120)
    category_filter = _as_text(category, 120)
    verified_filter = _boolean_filter(verified)
    urgent_filter = _boolean_filter(urgent)

    cars = await list_marketplace_cars(
        query=q,
        city=city_filter,
        brand=brand_filter,
        model=model_filter,
        verified=verified_filter,
        limit=limit,
    )

    services = await list_marketplace_services(
        query=q,
        city=city_filter,
        category=category_filter,
        verified=verified_filter,
        urgent=urgent_filter,
        limit=limit,
    )

    sellers = await list_featured_sellers(
        query=q,
        city=city_filter,
        limit=8,
    )

    summary = await marketplace_summary()

    context = marketing_context(request, title, description, path)
    context.update(
        {
            "buyer_mode": True,
            "lead_sent": request.query_params.get("lead") == "sent",
            "search_query": q or "",
            "selected_city": city_filter or "",
            "selected_brand": brand_filter or "",
            "selected_model": model_filter or "",
            "selected_category": category_filter or "",
            "selected_urgent": bool(urgent_filter),
            "selected_verified": bool(verified_filter),
            "marketplace_cars": [dict(item) for item in cars],
            "marketplace_services": [dict(item) for item in services],
            "featured_sellers": [dict(item) for item in sellers],
            "marketplace_summary": dict(summary) if summary else {},
        }
    )

    return context


async def tg_file_url(bot: Bot, file_id: str) -> str:
    file = await bot.get_file(file_id)

    return f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"


# ================= MARKETING PAGES =================

@router.get("/", response_class=HTMLResponse)
async def marketing_home(request: Request):
    host_subdomain = extract_subdomain_from_host(request.headers.get("host"))

    if host_subdomain:
        return await _render_site_by_subdomain(host_subdomain, request)

    return templates.TemplateResponse(
        "marketing/index.html",
        marketing_context(
            request,
            "Carpot — сайти для авторозборок, автосервісів та автозапчастин",
            "Telegram-платформа для створення сайтів, каталогів і заявок для авторозборок, СТО, шиномонтажу, евакуаторів та продавців автозапчастин.",
            "/",
        ),
    )


@router.get("/seller", response_class=HTMLResponse)
async def seller_home(request: Request):
    return templates.TemplateResponse(
        "marketing/index.html",
        marketing_context(
            request,
            "Carpot — сайти для авторозборок, автосервісів та автозапчастин",
            "Telegram-платформа для створення сайтів, каталогів і заявок для авторозборок, СТО, шиномонтажу, евакуаторів та продавців автозапчастин.",
            "/seller",
        ),
    )


@router.get("/buyer", response_class=HTMLResponse)
async def buyer_home(request: Request):
    return templates.TemplateResponse(
        "marketing/buyer.html",
        await buyer_marketplace_context(
            request,
            "Покупець CarPot — знайти авто, запчастини або автопослуги",
            "Пошук авто, запчастин, сервісів, продавців і заявок у єдиній CarPot-екосистемі з продовженням у Telegram.",
            "/buyer",
            limit=9,
        ),
    )


@router.get("/search", response_class=HTMLResponse)
async def buyer_search(
    request: Request,
    q: str | None = None,
    city: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    category: str | None = None,
    urgent: str | None = None,
    verified: str | None = None,
):
    return templates.TemplateResponse(
        "marketing/catalog.html",
        await buyer_marketplace_context(
            request,
            "Пошук CarPot — авто, послуги, продавці та категорії",
            "Єдиний пошук CarPot по авто, автопослугах, продавцях і категоріях з фільтрами міста, бренду, моделі та перевірених бізнесів.",
            "/search",
            query=q,
            city=city,
            brand=brand,
            model=model,
            category=category,
            urgent=urgent,
            verified=verified,
            limit=18,
        ),
    )


@router.get("/cars", response_class=HTMLResponse)
async def buyer_cars(
    request: Request,
    q: str | None = None,
    city: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    verified: str | None = None,
):
    context = await buyer_marketplace_context(
        request,
        "Каталог авто CarPot — авто в наявності та на розборі",
        "Каталог автомобілів і авто на розборі в CarPot з фільтрами міста, бренду, моделі та перевірених продавців.",
        "/cars",
        query=q,
        city=city,
        brand=brand,
        model=model,
        verified=verified,
        limit=24,
    )

    context["catalog_focus"] = "cars"

    return templates.TemplateResponse("marketing/catalog.html", context)


@router.get("/services", response_class=HTMLResponse)
async def buyer_services(
    request: Request,
    q: str | None = None,
    city: str | None = None,
    category: str | None = None,
    urgent: str | None = None,
    verified: str | None = None,
):
    context = await buyer_marketplace_context(
        request,
        "Автопослуги CarPot — СТО, евакуатор, шиномонтаж, автоелектрик",
        "Каталог автопослуг CarPot: евакуатор, СТО, шиномонтаж, автоелектрик та інші перевірені виконавці з Telegram-продовженням.",
        "/services",
        query=q,
        city=city,
        category=category,
        urgent=urgent,
        verified=verified,
        limit=24,
    )

    context["catalog_focus"] = "services"

    return templates.TemplateResponse("marketing/catalog.html", context)


@router.get("/catalog", response_class=HTMLResponse)
async def buyer_catalog(
    request: Request,
    q: str | None = None,
    city: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    category: str | None = None,
    urgent: str | None = None,
    verified: str | None = None,
):
    return templates.TemplateResponse(
        "marketing/catalog.html",
        await buyer_marketplace_context(
            request,
            "Каталог CarPot — авто, послуги, продавці та сайти",
            "Об'єднаний каталог CarPot для покупців: авто, автопослуги, авторозборки, продавці та SEO-ready категорії.",
            "/catalog",
            query=q,
            city=city,
            brand=brand,
            model=model,
            category=category,
            urgent=urgent,
            verified=verified,
            limit=24,
        ),
    )


@router.post("/buyer/lead")
async def create_buyer_platform_lead(
    request: Request,
    what_needed: str = Form(...),
    phone: str = Form(...),
    city: str | None = Form(None),
    telegram: str | None = Form(None),
    vin: str | None = Form(None),
    description: str | None = Form(None),
    photos: str | None = Form(None),
):
    await create_buyer_lead(
        what_needed=_short_text(what_needed, 500) or "Потрібна допомога з підбором",
        phone=_short_text(phone, 80) or "",
        city=_short_text(city, 120),
        telegram=_short_text(telegram, 120),
        vin=_short_text(vin, 80),
        description=_short_text(description, 2000),
        photos=_short_text(photos, 1000),
        source_path=_short_text(str(request.url.path), 500),
    )

    return RedirectResponse(url="/buyer?lead=sent#request", status_code=303)


@router.get("/privacy-policy", response_class=HTMLResponse)
async def marketing_privacy_policy(request: Request):
    return templates.TemplateResponse(
        "marketing/privacy_policy.html",
        marketing_context(
            request,
            "Політика конфіденційності — Carpot",
            "Політика конфіденційності Carpot: які дані обробляються для Telegram-бота, сайтів, заявок і комунікації.",
            "/privacy-policy",
        ),
    )


@router.get("/terms", response_class=HTMLResponse)
async def marketing_terms(request: Request):
    return templates.TemplateResponse(
        "marketing/terms.html",
        marketing_context(
            request,
            "Умови користування — Carpot",
            "Умови користування Carpot: Telegram-бот, конструктор сайтів, демо-шаблони, пакети, реклама та відповідальність користувача.",
            "/terms",
        ),
    )


@router.get("/contacts", response_class=HTMLResponse)
async def marketing_contacts(request: Request):
    return templates.TemplateResponse(
        "marketing/contacts.html",
        marketing_context(
            request,
            "Контакти — Carpot",
            "Контакти Carpot: Telegram-бот, email підтримки, локація в Україні та посилання на демо сайти для автомобільного бізнесу.",
            "/contacts",
        ),
    )


SEO_SEARCH_PAGES = {
    "evakuator-kyiv": ("евакуатор", "Київ"),
    "shynomontazh-lviv": ("шиномонтаж", "Львів"),
    "bmw-parts": ("BMW запчастини", None),
    "audi-a6-headlights": ("Audi A6 фара", None),
}


@router.get("/{seo_slug}", response_class=HTMLResponse)
async def buyer_seo_search_page(seo_slug: str, request: Request):
    seo_config = SEO_SEARCH_PAGES.get(seo_slug)

    if not seo_config:
        raise HTTPException(status_code=404)

    seo_query, seo_city = seo_config

    return templates.TemplateResponse(
        "marketing/catalog.html",
        await buyer_marketplace_context(
            request,
            f"CarPot — {seo_query} {seo_city or ''}".strip(),
            "SEO-ready buyer route CarPot для пошуку авто, запчастин, послуг і продавців у єдиній marketplace-екосистемі.",
            f"/{seo_slug}",
            query=seo_query,
            city=seo_city,
            limit=18,
        ),
    )


# ================= SITE RENDER =================

async def _render_site_by_subdomain(subdomain: str, request: Request):
    if not is_valid_subdomain(subdomain):
        raise HTTPException(status_code=404)

    site = await get_site_by_subdomain(subdomain)

    if not site or site["status"] != "active":
        raise HTTPException(
            status_code=404,
            detail="Site not found",
        )

    raw_config = site.get("config_live") or {}

    if isinstance(raw_config, str):
        try:
            raw_config = json.loads(raw_config)
        except Exception:
            raw_config = {}

    config = merge_with_default(raw_config)
    demo_preset = get_demo_render_preset(subdomain)

    if demo_preset:
        config = merge_with_default(demo_preset["config"])

    modules = config.setdefault("modules", {})
    products = config.setdefault("products", {})

    service_prices = (
        config
        .setdefault("services", {})
        .setdefault("prices", {})
    )

    car_titles = (
        config
        .setdefault("cars", {})
        .setdefault("titles", {})
    )

    car_prices = (
        config
        .setdefault("cars", {})
        .setdefault("prices", {})
    )

    # ================= LOGO =================

    if config.get("header", {}).get("logo"):
        logo = config["header"]["logo"]

        if isinstance(logo, str) and logo.startswith(("http://", "https://")):
            pass
        else:
            try:
                config["header"]["logo"] = await tg_file_url(bot, logo)
            except Exception:
                config["header"]["logo"] = None

    # ================= BANNERS =================

    if config.get("hero", {}).get("banners"):
        resolved = []

        for banner in config["hero"]["banners"]:
            if isinstance(banner, str) and banner.startswith(("http://", "https://")):
                resolved.append(banner)
                continue

            try:
                resolved.append(await tg_file_url(bot, banner))
            except Exception:
                continue

        config["hero"]["banners"] = resolved

    seller_id = site["seller_id"]
    seller = await get_seller_by_id(seller_id)

    cars = []
    services = []

    # ================= CARS =================

    if modules.get("cars", True):
        cars = await get_cars_by_seller(seller_id)
        cars = [dict(c) for c in cars]

        for car in cars:
            car_id = str(car.get("id"))

            car["title"] = (
                car_titles.get(car_id)
                or f"{car.get('brand', '')} {car.get('model', '')}".strip()
            )

            car["price"] = car_prices.get(car_id) or ""
            car["photo_url"] = None

            if car.get("photo_id"):
                try:
                    car["photo_url"] = await tg_file_url(bot, car["photo_id"])
                except Exception:
                    car["photo_url"] = None

    # ================= SERVICES =================

    if modules.get("services", True):
        services = await get_services_by_seller(seller_id)
        services = [dict(s) for s in services]

        for service in services:
            service_id = str(service.get("id"))

            service_price = service_prices.get(service_id)

            if service_price is None or service_price == "":
                service_price = service.get("price")

            if service_price is None or service_price == "":
                service_price = service.get("website") or ""

            service["price"] = service_price
            service["photo_url"] = None

            if service.get("photo_id"):
                photo_id = service["photo_id"]

                if isinstance(photo_id, str) and photo_id.startswith(("http://", "https://")):
                    service["photo_url"] = photo_id
                else:
                    try:
                        service["photo_url"] = await tg_file_url(bot, photo_id)
                    except Exception:
                        service["photo_url"] = None

        if not services:
            logger.warning(
                "SITE DEBUG empty services subdomain=%s seller_id=%s modules=%s",
                subdomain,
                seller_id,
                modules,
            )

    if demo_preset:
        demo_key = demo_preset["demo_type"]
        services = []

        for index, service in enumerate(demo_preset.get("services", []), start=1):
            demo_service = dict(service)
            demo_service["id"] = f"demo-{demo_key}-{index}"
            demo_service["seller_id"] = seller_id
            demo_service["photo_url"] = (
                demo_service.get("photo_id")
                if isinstance(demo_service.get("photo_id"), str)
                and demo_service.get("photo_id").startswith(("http://", "https://"))
                else None
            )
            services.append(demo_service)

    return templates.TemplateResponse(
        "site.html",
        {
            "request": request,
            "subdomain": subdomain,
            "site_id": site.get("id"),
            "config": config,
            "seller": seller,
            "cars": cars,
            "services": services,
            "products": products,
        },
    )


@router.get("/site/{subdomain}", response_class=HTMLResponse)
async def render_site(subdomain: str, request: Request):
    return await _render_site_by_subdomain(subdomain, request)


# ================= LEAD FORM =================

async def _create_lead_for_subdomain(
    subdomain: str,
    name: str,
    phone: str,
    message: str,
    session_id: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    referrer: str | None = None,
):
    if not is_valid_subdomain(subdomain):
        raise HTTPException(status_code=404)

    site = await get_site_by_subdomain(subdomain)

    if not site or site["status"] != "active":
        raise HTTPException(status_code=404)

    seller = await get_seller_by_id(site["seller_id"])

    if not seller:
        raise HTTPException(status_code=404)

    try:
        await create_site_lead(
            seller_id=seller["id"],
            site_id=site.get("id"),
            subdomain=subdomain,
            name=name or None,
            phone=phone,
            message=message or None,
            session_id=_short_text(session_id, 120),
            utm_source=_short_text(utm_source, 200),
            utm_medium=_short_text(utm_medium, 200),
            utm_campaign=_short_text(utm_campaign, 200),
            referrer=_short_text(referrer, 1000),
        )
    except Exception:
        logger.exception("Failed to save site lead for subdomain %s", subdomain)

    text = (
        f"📩 Нова заявка з сайту\n\n"
        f"👤 Ім'я: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"💬 Повідомлення: {message or '-'}\n"
        f"🌐 Сайт: {subdomain}"
    )

    await send_message_to_seller(seller["telegram_id"], text)

    return {"status": "ok"}


@router.post("/site/{subdomain}/lead")
async def create_lead(
    subdomain: str,
    name: str = Form(...),
    phone: str = Form(...),
    message: str = Form(""),
    session_id: str | None = Form(None),
    utm_source: str | None = Form(None),
    utm_medium: str | None = Form(None),
    utm_campaign: str | None = Form(None),
    referrer: str | None = Form(None),
):
    return await _create_lead_for_subdomain(
        subdomain,
        name,
        phone,
        message,
        session_id,
        utm_source,
        utm_medium,
        utm_campaign,
        referrer,
    )


@router.post("/lead")
async def create_host_lead(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    message: str = Form(""),
    session_id: str | None = Form(None),
    utm_source: str | None = Form(None),
    utm_medium: str | None = Form(None),
    utm_campaign: str | None = Form(None),
    referrer: str | None = Form(None),
):
    host_subdomain = extract_subdomain_from_host(request.headers.get("host"))

    if not host_subdomain:
        raise HTTPException(status_code=404)

    return await _create_lead_for_subdomain(
        host_subdomain,
        name,
        phone,
        message,
        session_id,
        utm_source,
        utm_medium,
        utm_campaign,
        referrer,
    )


# ================= ANALYTICS =================

@router.post("/analytics/session")
async def analytics_session(request: Request):
    payload = await _analytics_payload(request)
    session_id = _short_text(payload.get("session_id"), 120)

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    user_agent = _short_text(
        request.headers.get("user-agent") or payload.get("user_agent"),
        600,
    )

    detected_device, detected_browser, detected_os = _detect_client(user_agent)

    device_type = _short_text(payload.get("device_type"), 40) or detected_device

    if device_type not in VALID_DEVICE_TYPES:
        device_type = detected_device

    try:
        await upsert_session(
            session_id=session_id,
            seller_site_id=_optional_int(payload.get("seller_site_id")),
            subdomain=_short_text(payload.get("subdomain"), 120),
            landing_page=_short_text(payload.get("landing_page"), 1000),
            current_page=_short_text(payload.get("current_page"), 1000),
            referrer=_short_text(payload.get("referrer"), 1000),
            utm_source=_short_text(payload.get("utm_source"), 200),
            utm_medium=_short_text(payload.get("utm_medium"), 200),
            utm_campaign=_short_text(payload.get("utm_campaign"), 200),
            utm_content=_short_text(payload.get("utm_content"), 200),
            utm_term=_short_text(payload.get("utm_term"), 200),
            ip_address=_client_ip(request),
            country=_short_text(request.headers.get("cf-ipcountry"), 120),
            city=None,
            device_type=device_type,
            browser=_short_text(payload.get("browser"), 120) or detected_browser,
            operating_system=_short_text(payload.get("operating_system"), 120) or detected_os,
            language=_short_text(
                payload.get("language") or request.headers.get("accept-language"),
                120,
            ),
            user_agent=user_agent,
            time_on_site_seconds=int(payload.get("time_on_site_seconds") or 0),
        )
    except Exception:
        logger.exception("Failed to save analytics session")

    return JSONResponse({"ok": True})


@router.post("/analytics/event")
async def analytics_event(request: Request):
    payload = await _analytics_payload(request)
    session_id = _short_text(payload.get("session_id"), 120)
    event_type = _short_text(payload.get("event_type"), 80)

    if not session_id or event_type not in ALLOWED_ANALYTICS_EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid analytics event")

    try:
        await add_event(
            session_id=session_id,
            seller_site_id=_optional_int(payload.get("seller_site_id")),
            subdomain=_short_text(payload.get("subdomain"), 120),
            event_type=event_type,
            event_name=_short_text(payload.get("event_name"), 200),
            event_target=_short_text(payload.get("event_target"), 500),
            page_url=_short_text(payload.get("page_url"), 1000),
        )
    except Exception:
        logger.exception("Failed to save analytics event")

    return JSONResponse({"ok": True})


# ================= ROUTERS =================

app.include_router(liqpay_router)
app.include_router(crm_router)
app.include_router(seller_crm_router)
app.include_router(router)