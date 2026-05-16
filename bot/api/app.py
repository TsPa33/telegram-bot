import json
import logging
import re
from urllib.parse import urlencode

from aiogram import Bot
from fastapi import APIRouter, FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
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
from bot.services.buyer_request_service import (
    BuyerRequestInput,
    BuyerRequestValidationError,
    submit_marketplace_buyer_request,
)
from bot.services.buyer_offer_service import (
    accept_offer_for_buyer,
    get_buyer_offer_comparison,
)
from bot.database.repositories.marketplace_repo import (
    get_featured_sellers,
    get_latest_cars,
    get_latest_services,
    get_marketplace_summary,
    search_marketplace,
)
from bot.database.repositories.ai_search_repo import log_ai_search
from bot.services.ai_request_interpreter import interpret_buyer_request, normalize_query
from bot.services.marketplace_search import run_priority_marketplace_search
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



def _normalize_phone(value: str | None) -> str | None:
    value = _short_text(value, 40)
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    if value.startswith("+") and 9 <= len(digits) <= 15:
        return f"+{digits}"
    if len(digits) == 10 and digits.startswith("0"):
        return f"+38{digits}"
    if len(digits) == 12 and digits.startswith("380"):
        return f"+{digits}"
    if 9 <= len(digits) <= 15:
        return f"+{digits}"
    return value


def _buyer_filter_context(results: dict | None = None, **overrides) -> dict:
    results = results or {}
    selected = {
        "search_query": results.get("query", overrides.get("q", "")),
        "selected_city": results.get("city", overrides.get("city", "")),
        "selected_type": results.get("type", overrides.get("type", "all")),
        "selected_category": results.get("category", overrides.get("category", "")),
        "selected_service_type": results.get("service_type", overrides.get("service_type", "")),
        "selected_brand": results.get("brand", overrides.get("brand", "")),
        "selected_condition": results.get("condition", overrides.get("condition", "")),
        "selected_verified": results.get("verified", overrides.get("verified", "")),
        "selected_sort": results.get("sort", overrides.get("sort", "new")) or "new",
    }
    pagination_params = {
        "q": selected["search_query"],
        "city": selected["selected_city"],
        "type": selected["selected_type"],
        "category": selected["selected_category"],
        "service_type": selected["selected_service_type"],
        "brand": selected["selected_brand"],
        "condition": selected["selected_condition"],
        "verified": selected["selected_verified"],
        "sort": selected["selected_sort"],
    }
    pagination_query = urlencode({key: value for key, value in pagination_params.items() if value})
    selected["pagination_query"] = f"&{pagination_query}" if pagination_query else ""
    return selected


def _record_to_plain(value):
    if isinstance(value, dict):
        return {key: _record_to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_record_to_plain(item) for item in value]
    if hasattr(value, "items"):
        return {key: _record_to_plain(item) for key, item in dict(value).items()}
    return value


def _ai_search_query(interpretation: dict, raw_query: str) -> str:
    terms = [
        interpretation.get("part_name"),
        interpretation.get("service_type"),
        interpretation.get("brand"),
        interpretation.get("model"),
        interpretation.get("generation"),
        interpretation.get("engine"),
    ]
    compact_terms = [str(term).strip() for term in terms if str(term or "").strip()]
    if compact_terms:
        return " ".join(dict.fromkeys(compact_terms))[:240]
    search_terms = interpretation.get("search_terms") or []
    if isinstance(search_terms, list) and search_terms:
        return " ".join(str(term).strip() for term in search_terms if str(term or "").strip())[:240]
    return (interpretation.get("normalized_query") or raw_query or "")[:240]


def _ai_search_type(interpretation: dict) -> str:
    intent = interpretation.get("intent")
    category = interpretation.get("category")
    if intent == "service_search" or category == "services":
        return "services"
    if intent == "car_search" or category == "cars":
        return "cars"
    return "all"


def _ai_request_prefill(interpretation: dict, raw_query: str) -> dict:
    category = interpretation.get("category") or "unknown"
    request_type = "other"
    request_category = "other"
    if category == "parts":
        request_type = "part"
        request_category = "parts"
    elif category == "services":
        service_type = (interpretation.get("service_type") or "").lower()
        request_type = "service"
        request_category = "service"
        if "евакуатор" in service_type:
            request_type = "tow"
            request_category = "tow"
        elif "діаг" in service_type or "диаг" in service_type:
            request_type = "diagnostics"
            request_category = "diagnostics"
        elif "шин" in service_type:
            request_category = "tires"
    elif category == "cars":
        request_type = "car"
        request_category = "cars"

    urgency = interpretation.get("urgency") or "normal"
    request_urgency = {"urgent": "today", "normal": "soon", "low": "flexible"}.get(urgency, "soon")
    need = interpretation.get("part_name") or interpretation.get("service_type") or ""
    description = raw_query or interpretation.get("normalized_query") or ""
    if need and need.lower() not in description.lower():
        description = f"{need}: {description}".strip()

    return {
        "query": description[:1400],
        "category": request_category,
        "request_type": request_type,
        "brand": interpretation.get("brand") or "",
        "model": interpretation.get("model") or interpretation.get("generation") or "",
        "city": interpretation.get("city") or "",
        "vin": interpretation.get("vin") or "",
        "urgency": request_urgency,
        "part_name": interpretation.get("part_name") or "",
        "service_type": interpretation.get("service_type") or "",
    }


def _ai_results_count(results: dict) -> int:
    return len(results.get("cars") or []) + len(results.get("services") or []) + len(results.get("sellers") or [])


def _should_create_request(interpretation: dict, result_count: int) -> bool:
    confidence = float(interpretation.get("confidence") or 0)
    return confidence < 0.7 or result_count == 0 or bool(interpretation.get("clarification_needed"))

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
    }


async def tg_file_url(bot: Bot, file_id: str) -> str:
    file = await bot.get_file(file_id)

    return (
        f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    )


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
        ),
    )


@router.get("/seller", response_class=HTMLResponse)
async def marketing_seller(request: Request):
    return templates.TemplateResponse(
        "marketing/index.html",
        marketing_context(
            request,
            "Carpot — сайти для авторозборок, автосервісів та автозапчастин",
            "Telegram-платформа для створення сайтів, каталогів і заявок для авторозборок, СТО, шиномонтажу, евакуаторів та продавців автозапчастин.",
            "/seller",
        ),
    )


async def _safe_buyer_context() -> dict:
    try:
        summary = await get_marketplace_summary()
        latest_cars = await get_latest_cars(limit=6)
        latest_services = await get_latest_services(limit=6)
        featured_sellers = await get_featured_sellers(limit=6)
    except Exception:
        logger.exception("Failed to load buyer marketplace context")
        summary = {
            "cars_count": 0,
            "services_count": 0,
            "sellers_count": 0,
            "cities_count": 0,
        }
        latest_cars = []
        latest_services = []
        featured_sellers = []

    return {
        "marketplace_summary": summary,
        "marketplace_cars": latest_cars,
        "marketplace_services": latest_services,
        "featured_sellers": featured_sellers,
    }


@router.get("/buyer", response_class=HTMLResponse)
async def buyer_home(request: Request):
    context = marketing_context(
        request,
        "CarPot для покупця — пошук автозапчастин, авто та послуг",
        "Покупець CarPot знаходить автозапчастини, авто, СТО, евакуаторів та інших автомобільних продавців через Telegram-екосистему й публічний каталог.",
        "/buyer",
    )
    context.update(await _safe_buyer_context())
    return templates.TemplateResponse("marketing/buyer.html", context)


@router.get("/catalog", response_class=HTMLResponse)
async def buyer_catalog(
    request: Request,
    page: int = 1,
    q: str | None = None,
    city: str | None = None,
    category: str | None = None,
    service_type: str | None = None,
    brand: str | None = None,
    condition: str | None = None,
    verified: str | None = None,
    sort: str = "new",
):
    page = max(page, 1)
    limit = 12
    offset = (page - 1) * limit

    try:
        summary = await get_marketplace_summary()
        results = await search_marketplace(
            q=q,
            city=city,
            item_type="all",
            limit=limit,
            offset=offset,
            category=category,
            service_type=service_type,
            brand=brand,
            condition=condition,
            verified=verified,
            sort=sort,
        )
        sellers = results["sellers"] or await get_featured_sellers(limit=8)
    except Exception:
        logger.exception("Failed to load buyer catalog")
        summary = {"cars_count": 0, "services_count": 0, "sellers_count": 0, "cities_count": 0}
        results = {"cars": [], "services": [], "sellers": [], "query": q or "", "city": city or "", "type": "all"}
        sellers = []

    context = marketing_context(
        request,
        "Каталог CarPot — авто, запчастини, сервіси та продавці",
        "Публічний каталог активних авто, автосервісів і продавців CarPot для покупців.",
        "/catalog",
    )
    context.update({
        "marketplace_summary": summary,
        "marketplace_cars": results["cars"],
        "marketplace_services": results["services"],
        "featured_sellers": sellers,
        "page": page,
        "catalog_type": "all",
        "filter_action": "/catalog",
    })
    context.update(_buyer_filter_context(results, type="all"))
    return templates.TemplateResponse("marketing/catalog.html", context)


@router.get("/cars", response_class=HTMLResponse)
async def buyer_cars(
    request: Request,
    page: int = 1,
    city: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    condition: str | None = None,
    verified: str | None = None,
    sort: str = "new",
):
    page = max(page, 1)
    limit = 18
    offset = (page - 1) * limit

    try:
        results = await search_marketplace(
            city=city,
            item_type="cars",
            limit=limit,
            offset=offset,
            category=category,
            brand=brand,
            condition=condition,
            verified=verified,
            sort=sort,
        )
        cars = results["cars"]
        summary = await get_marketplace_summary()
    except Exception:
        logger.exception("Failed to load buyer cars")
        results = {"cars": [], "query": "", "city": city or "", "type": "cars"}
        cars = []
        summary = {"cars_count": 0, "services_count": 0, "sellers_count": 0, "cities_count": 0}

    context = marketing_context(
        request,
        "Авто та запчастини CarPot — каталог для покупця",
        "Активні авто й пропозиції продавців CarPot з контактами та описами.",
        "/cars",
    )
    context.update({"marketplace_cars": cars, "marketplace_summary": summary, "page": page, "filter_action": "/cars"})
    context.update(_buyer_filter_context(results, type="cars"))
    return templates.TemplateResponse("marketing/cars.html", context)


@router.get("/services", response_class=HTMLResponse)
async def buyer_services(
    request: Request,
    page: int = 1,
    city: str | None = None,
    category: str | None = None,
    service_type: str | None = None,
    verified: str | None = None,
    sort: str = "new",
):
    page = max(page, 1)
    limit = 18
    offset = (page - 1) * limit

    try:
        results = await search_marketplace(
            city=city,
            item_type="services",
            limit=limit,
            offset=offset,
            category=category,
            service_type=service_type,
            verified=verified,
            sort=sort,
        )
        services = results["services"]
        summary = await get_marketplace_summary()
    except Exception:
        logger.exception("Failed to load buyer services")
        results = {"services": [], "query": "", "city": city or "", "type": "services"}
        services = []
        summary = {"cars_count": 0, "services_count": 0, "sellers_count": 0, "cities_count": 0}

    context = marketing_context(
        request,
        "Автосервіси CarPot — каталог послуг для покупця",
        "СТО, автоелектрики, шиномонтаж, евакуатори та інші автомобільні послуги в каталозі CarPot.",
        "/services",
    )
    context.update({"marketplace_services": services, "marketplace_summary": summary, "page": page, "filter_action": "/services"})
    context.update(_buyer_filter_context(results, type="services"))
    return templates.TemplateResponse("marketing/services.html", context)


@router.get("/search", response_class=HTMLResponse)
async def buyer_search(
    request: Request,
    q: str | None = None,
    city: str | None = None,
    type: str = "all",
    page: int = 1,
    category: str | None = None,
    service_type: str | None = None,
    brand: str | None = None,
    condition: str | None = None,
    verified: str | None = None,
    sort: str = "new",
):
    page = max(page, 1)
    limit = 12
    offset = (page - 1) * limit

    try:
        results = await search_marketplace(
            q=q,
            city=city,
            item_type=type,
            limit=limit,
            offset=offset,
            category=category,
            service_type=service_type,
            brand=brand,
            condition=condition,
            verified=verified,
            sort=sort,
        )
        summary = await get_marketplace_summary()
    except Exception:
        logger.exception("Failed to search buyer marketplace")
        results = {"cars": [], "services": [], "sellers": [], "query": (q or "").strip(), "city": (city or "").strip(), "type": type}
        summary = {"cars_count": 0, "services_count": 0, "sellers_count": 0, "cities_count": 0}

    context = marketing_context(
        request,
        "Пошук CarPot — знайти авто, запчастини або сервіс",
        "Пошук по каталогу CarPot: авто, запчастини, продавці, СТО, евакуатори та автопослуги за містом або запитом.",
        "/search",
    )
    context.update({
        "marketplace_summary": summary,
        "marketplace_cars": results["cars"],
        "marketplace_services": results["services"],
        "featured_sellers": results["sellers"],
        "page": page,
        "catalog_type": "search",
        "filter_action": "/search",
    })
    context.update(_buyer_filter_context(results))
    return templates.TemplateResponse("marketing/catalog.html", context)


@router.post("/buyer/ai-search")
async def buyer_ai_search(request: Request):
    raw_query = None
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        raw_query = body.get("query")
    else:
        form = await request.form()
        raw_query = form.get("query")

    raw_query = normalize_query(raw_query)
    if not raw_query:
        interpretation = await interpret_buyer_request(raw_query)
        results = {"cars": [], "services": [], "sellers": [], "query": "", "city": "", "type": "all"}
        result_count = 0
        response_payload = {
            "ok": True,
            "interpretation": interpretation,
            "results": results,
            "result_count": result_count,
            "should_create_request": True,
            "prefill": _ai_request_prefill(interpretation, raw_query),
            "search_url": "/search",
        }
        return JSONResponse(response_payload)

    interpretation = await interpret_buyer_request(raw_query)
    try:
        item_type = _ai_search_type(interpretation)
        search_query = _ai_search_query(interpretation, raw_query)
        if interpretation.get("intent") == "parts_search" or interpretation.get("category") == "parts":
            results = await run_priority_marketplace_search(
                interpretation=interpretation,
                raw_query=raw_query,
                search_query=search_query,
                limit=9,
            )
        else:
            results = await search_marketplace(
                q=search_query,
                city=interpretation.get("city"),
                item_type=item_type,
                limit=9,
                offset=0,
                category=interpretation.get("category") if interpretation.get("category") != "unknown" else None,
                service_type=interpretation.get("service_type"),
                brand=interpretation.get("brand"),
                sort="trusted" if float(interpretation.get("confidence") or 0) >= 0.75 else "new",
            )
    except Exception:
        logger.exception("Buyer AI marketplace search failed; returning safe empty result")
        results = {"cars": [], "services": [], "sellers": [], "query": raw_query, "city": interpretation.get("city") or "", "type": "all", "decisions": [], "primary_result_type": "marketplace_request_fallback"}

    result_count = _ai_results_count(results)
    should_create_request = bool(results.get("should_create_request", _should_create_request(interpretation, result_count)))
    prefill = _ai_request_prefill(interpretation, raw_query)
    search_params = {
        "q": results.get("query") or raw_query,
        "city": results.get("city") or interpretation.get("city") or "",
        "type": results.get("type") or _ai_search_type(interpretation),
        "category": results.get("category") or "",
        "service_type": results.get("service_type") or "",
        "brand": results.get("brand") or "",
    }
    search_url = "/search?" + urlencode({key: value for key, value in search_params.items() if value})

    await log_ai_search(
        raw_query=raw_query,
        normalized_query=interpretation.get("normalized_query"),
        intent=interpretation.get("intent"),
        category=interpretation.get("category"),
        confidence=interpretation.get("confidence"),
        clarification_needed=bool(interpretation.get("clarification_needed")),
        result_count=result_count,
    )

    response_payload = {
        "ok": True,
        "interpretation": interpretation,
        "results": _record_to_plain(results),
        "result_count": result_count,
        "should_create_request": should_create_request,
        "prefill": prefill,
        "search_url": search_url,
        "decisions": _record_to_plain(results.get("decisions") or []),
        "primary_result_type": results.get("primary_result_type") or "marketplace_request_fallback",
        "fallback": _record_to_plain(results.get("fallback") or {}),
    }

    wants_json = "application/json" in request.headers.get("accept", "") or "application/json" in content_type
    if wants_json:
        return JSONResponse(content=jsonable_encoder(response_payload))

    summary = await get_marketplace_summary()
    sellers = results.get("sellers") or await get_featured_sellers(limit=8)
    context = marketing_context(
        request,
        "AI-пошук CarPot — знайти авто, запчастини або сервіс",
        "AI-інтерпретація buyer-запиту CarPot із безпечним fallback та маркетплейс-пошуком.",
        "/catalog",
    )
    context.update({
        "marketplace_summary": summary,
        "marketplace_cars": results.get("cars") or [],
        "marketplace_services": results.get("services") or [],
        "featured_sellers": sellers,
        "page": 1,
        "catalog_type": "ai-search",
        "filter_action": "/search",
        "ai_search_response": response_payload,
    })
    context.update(_buyer_filter_context(results))
    return templates.TemplateResponse("marketing/catalog.html", context)


@router.post("/buyer/requests")
async def buyer_request_submit(
    request: Request,
    name: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    buyer_telegram: str | None = Form(default=None),
    city: str | None = Form(default=None),
    request_type: str | None = Form(default="part"),
    category: str | None = Form(default="parts"),
    brand: str | None = Form(default=None),
    model: str | None = Form(default=None),
    vin: str | None = Form(default=None),
    query: str = Form(...),
    urgency: str | None = Form(default="soon"),
    website: str | None = Form(default=None),
    lead_started_at: str | None = Form(default=None),
    photos: list[UploadFile] | None = File(default=None),
):
    if _short_text(website, 80):
        return JSONResponse({"ok": True, "request_id": None})

    payload = BuyerRequestInput(
        buyer_name=name,
        buyer_phone=phone,
        buyer_telegram=buyer_telegram,
        city=city,
        request_type=request_type,
        category=category,
        brand=brand,
        model=model,
        vin=vin,
        description=query,
        urgency=urgency,
        photos=photos,
    )

    try:
        result = await submit_marketplace_buyer_request(payload)
        request_row = result.get("request")
    except BuyerRequestValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Failed to create buyer marketplace request")
        raise HTTPException(status_code=500, detail="Не вдалося зберегти заявку")

    wants_json = "application/json" in request.headers.get("accept", "")
    if wants_json:
        return JSONResponse({
            "ok": True,
            "request_id": request_row["id"] if request_row else None,
            "routing": result.get("routing_plan"),
        })

    return templates.TemplateResponse(
        "marketing/buyer.html",
        {
            **marketing_context(
                request,
                "CarPot для покупця — заявку отримано",
                "Заявка покупця CarPot збережена.",
                "/buyer",
            ),
            **await _safe_buyer_context(),
            "lead_created": True,
        },
    )


@router.get("/requests/{request_id}/offers", response_class=HTMLResponse)
async def buyer_request_offers(request: Request, request_id: int):
    request_model = await get_buyer_offer_comparison(request_id)
    if not request_model:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")

    return templates.TemplateResponse(
        "marketing/buyer_offer_comparison.html",
        {
            **marketing_context(
                request,
                f"Пропозиції для заявки #{request_id} — CarPot",
                "Порівняння пропозицій продавців CarPot для покупця.",
                f"/requests/{request_id}/offers",
            ),
            "request_model": request_model,
        },
    )


@router.post("/requests/{request_id}/offers/{offer_id}/accept", response_class=HTMLResponse)
async def buyer_accept_offer(request: Request, request_id: int, offer_id: int):
    result = await accept_offer_for_buyer(request_id, offer_id)
    if not result.accepted:
        raise HTTPException(status_code=404, detail="Пропозицію не знайдено або її не можна обрати")

    request_model = await get_buyer_offer_comparison(request_id)
    if not request_model:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")

    wants_json = "application/json" in request.headers.get("accept", "")
    if wants_json:
        return JSONResponse({"ok": True, "request_id": request_id, "offer_id": offer_id, "match": result.match})

    return templates.TemplateResponse(
        "marketing/buyer_offer_comparison.html",
        {
            **marketing_context(
                request,
                f"Пропозицію обрано — заявка #{request_id} — CarPot",
                "Marketplace match створено, контакти продавця відкрито для покупця.",
                f"/requests/{request_id}/offers",
            ),
            "request_model": request_model,
            "offer_accepted": True,
        },
    )


@router.post("/buyer/leads")
async def buyer_lead_submit(
    request: Request,
    name: str | None = Form(default=None),
    phone: str | None = Form(default=None),
    query: str = Form(...),
    city: str | None = Form(default=None),
    vin: str | None = Form(default=None),
    website: str | None = Form(default=None),
    lead_started_at: str | None = Form(default=None),
):
    return await buyer_request_submit(
        request=request,
        name=name,
        phone=phone,
        buyer_telegram=None,
        city=city,
        request_type="part",
        category="parts",
        brand=None,
        model=None,
        vin=vin,
        query=query,
        urgency="soon",
        website=website,
        lead_started_at=lead_started_at,
        photos=None,
    )


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


# ================= SITE RENDER =================

async def _render_site_by_subdomain(subdomain: str, request: Request):
    if not is_valid_subdomain(subdomain):
        raise HTTPException(status_code=404)

    site = await get_site_by_subdomain(subdomain)

    if not site or site["status"] != "active":
        raise HTTPException(
            status_code=404,
            detail="Site not found"
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

    # ================= MEDIA =================

    # ===== LOGO =====

    if config.get("header", {}).get("logo"):
        logo = config["header"]["logo"]

        if isinstance(logo, str) and logo.startswith(
            ("http://", "https://")
        ):
            pass

        else:
            try:
                config["header"]["logo"] = await tg_file_url(
                    bot,
                    logo
                )

            except Exception:
                config["header"]["logo"] = None

    # ===== BANNERS =====

    if config.get("hero", {}).get("banners"):
        resolved = []

        for banner in config["hero"]["banners"]:

            # external URL
            if (
                isinstance(banner, str)
                and banner.startswith(("http://", "https://"))
            ):
                resolved.append(banner)
                continue

            # telegram file_id
            try:
                resolved.append(
                    await tg_file_url(bot, banner)
                )

            except Exception:
                continue

        config["hero"]["banners"] = resolved

    seller_id = site["seller_id"]

    # ================= SELLER =================

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

            car["price"] = (
                car_prices.get(car_id)
                or ""
            )

            car["photo_url"] = None

            if car.get("photo_id"):

                try:
                    car["photo_url"] = await tg_file_url(
                        bot,
                        car["photo_id"]
                    )

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
                        service["photo_url"] = await tg_file_url(
                            bot,
                            photo_id
                        )

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

    await send_message_to_seller(
        seller["telegram_id"],
        text
    )

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
        subdomain, name, phone, message, session_id, utm_source, utm_medium, utm_campaign, referrer
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
        host_subdomain, name, phone, message, session_id, utm_source, utm_medium, utm_campaign, referrer
    )


# ================= ANALYTICS =================

@router.post("/analytics/session")
async def analytics_session(request: Request):
    payload = await _analytics_payload(request)
    session_id = _short_text(payload.get("session_id"), 120)
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    user_agent = _short_text(request.headers.get("user-agent") or payload.get("user_agent"), 600)
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
            language=_short_text(payload.get("language") or request.headers.get("accept-language"), 120),
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
