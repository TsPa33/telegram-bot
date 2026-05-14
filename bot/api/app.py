import json
import logging

from aiogram import Bot
from fastapi import APIRouter, FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.api.liqpay_callback import router as liqpay_router
from bot.api.crm import router as crm_router
from bot.config import BOT_TOKEN

from bot.database.repositories.site_repo import get_site_by_subdomain
from bot.database.repositories.seller_repo import get_seller_by_id
from bot.database.repositories.car_repo import get_cars_by_seller
from bot.database.repositories.service_repo import get_services_by_seller
from bot.database.repositories.lead_repo import create_site_lead

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
):
    return await _create_lead_for_subdomain(subdomain, name, phone, message)


@router.post("/lead")
async def create_host_lead(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    message: str = Form(""),
):
    host_subdomain = extract_subdomain_from_host(request.headers.get("host"))

    if not host_subdomain:
        raise HTTPException(status_code=404)

    return await _create_lead_for_subdomain(host_subdomain, name, phone, message)


# ================= ROUTERS =================

app.include_router(liqpay_router)
app.include_router(crm_router)
app.include_router(router)
