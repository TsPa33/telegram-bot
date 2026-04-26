import json

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.api.liqpay_callback import router as liqpay_router
from bot.database.repositories.site_repo import get_site_by_subdomain
from bot.services.site_config import merge_with_default
from bot.utils.subdomain import is_valid_subdomain

app = FastAPI()
router = APIRouter()

templates = Jinja2Templates(directory="bot/api/templates")


@router.get("/site/{subdomain}", response_class=HTMLResponse)
async def render_site(subdomain: str, request: Request):
    # validation
    if not is_valid_subdomain(subdomain):
        raise HTTPException(status_code=404)

    site = await get_site_by_subdomain(subdomain)

    if not site or site["status"] != "active":
        raise HTTPException(status_code=404, detail="Site not found")

    # 🔥 FIX: обробка JSONB
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


app.include_router(liqpay_router)
app.include_router(router)
