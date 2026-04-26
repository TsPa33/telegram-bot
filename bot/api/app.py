import json

from fastapi import APIRouter, FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.api.liqpay_callback import router as liqpay_router
from bot.database.repositories.site_repo import get_site_by_subdomain
from bot.database.repositories.seller_repo import get_seller_by_id
from bot.services.site_config import merge_with_default
from bot.utils.subdomain import is_valid_subdomain
from bot.services.telegram_sender import send_message_to_seller

app = FastAPI()
router = APIRouter()

templates = Jinja2Templates(directory="bot/api/templates")


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

    return templates.TemplateResponse(
        "site.html",
        {
            "request": request,
            "subdomain": subdomain,
            "config": config,
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
