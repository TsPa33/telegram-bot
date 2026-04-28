import json

from aiogram import Bot
from fastapi import APIRouter, FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.api.liqpay_callback import router as liqpay_router
from bot.config import BOT_TOKEN
from bot.database.repositories.site_repo import get_site_by_subdomain
from bot.database.repositories.seller_repo import get_seller_by_id
from bot.database.repositories.car_repo import get_cars_by_seller
from bot.database.repositories.service_repo import get_services_by_seller
from bot.services.site_config import merge_with_default
from bot.utils.subdomain import is_valid_subdomain
from bot.services.telegram_sender import send_message_to_seller

app = FastAPI()
router = APIRouter()

templates = Jinja2Templates(directory="bot/api/templates")
bot = Bot(token=BOT_TOKEN)


async def tg_file_url(bot: Bot, file_id: str) -> str:
    file = await bot.get_file(file_id)
    return f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"


# ================= SITE RENDER =================

@router.get("/site/{subdomain}", response_class=HTMLResponse)
async def render_site(subdomain: str, request: Request):
    if not is_valid_subdomain(subdomain):
        raise HTTPException(status_code=404)

    site = await get_site_by_subdomain(subdomain)

    if not site or site["status"] != "active":
        raise HTTPException(status_code=404, detail="Site not found")

    raw_config = site.get("config_live") or {}

    if isinstance(raw_config, str):
        try:
            raw_config = json.loads(raw_config)
        except Exception:
            raw_config = {}

    config = merge_with_default(raw_config)

    modules = config.setdefault("modules", {})

    # MEDIA
    if config.get("header", {}).get("logo"):
        try:
            config["header"]["logo"] = await tg_file_url(bot, config["header"]["logo"])
        except Exception:
            config["header"]["logo"] = None

    if config.get("hero", {}).get("banners"):
        resolved = []
        for b in config["hero"]["banners"]:
            try:
                resolved.append(await tg_file_url(bot, b))
            except Exception:
                continue
        config["hero"]["banners"] = resolved

    seller_id = site["seller_id"]

    cars = []
    services = []

    # ================= FIX HERE =================

    if modules.get("cars", True):
        cars = await get_cars_by_seller(seller_id)
        cars = [dict(c) for c in cars]  # 🔥 FIX

        for car in cars:
            car["photo_url"] = None
            if car.get("photo_id"):
                try:
                    car["photo_url"] = await tg_file_url(bot, car["photo_id"])
                except Exception:
                    car["photo_url"] = None

    if modules.get("services", True):
        services = await get_services_by_seller(seller_id)
        services = [dict(s) for s in services]  # 🔥 FIX

        for service in services:
            service["photo_url"] = None
            if service.get("photo_id"):
                try:
                    service["photo_url"] = await tg_file_url(bot, service["photo_id"])
                except Exception:
                    service["photo_url"] = None

    # ===========================================

    return templates.TemplateResponse(
        "site.html",
        {
            "request": request,
            "subdomain": subdomain,
            "config": config,
            "cars": cars,
            "services": services,
        },
    )


# ================= LEAD FORM =================

@router.post("/site/{subdomain}/lead")
async def create_lead(
    subdomain: str,
    name: str = Form(...),
    phone: str = Form(...),
    message: str = Form(""),
):
    if not is_valid_subdomain(subdomain):
        raise HTTPException(status_code=404)

    site = await get_site_by_subdomain(subdomain)

    if not site or site["status"] != "active":
        raise HTTPException(status_code=404)

    seller = await get_seller_by_id(site["seller_id"])

    if not seller:
        raise HTTPException(status_code=404)

    text = (
        f"📩 Нова заявка з сайту\n\n"
        f"👤 Ім'я: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"💬 Повідомлення: {message or '-'}\n"
        f"🌐 Сайт: {subdomain}"
    )

    await send_message_to_seller(seller["telegram_id"], text)

    return {"status": "ok"}


# ================= ROUTERS =================

app.include_router(liqpay_router)
app.include_router(router)
