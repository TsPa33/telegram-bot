import json
import logging
import os
import secrets
import tempfile
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.database.repositories.car_repo import (
    create_seller_car,
    delete_seller_car,
    get_cars_by_seller,
    update_seller_car_description,
    update_seller_car_photo,
)
from bot.database.repositories.model_repo import (
    get_brands_with_ids,
    get_existing_model_id_by_brand_model_ids,
    get_model_id,
    get_models_by_brand_id,
    get_models_with_brand_ids,
)
from bot.database.repositories.seller_crm_repo import (
    SellerCrmGarageFullError,
    create_crm_session,
    create_seller_crm_car,
    delete_crm_session,
    get_crm_account_by_slug,
    get_crm_account_for_login,
    get_crm_session,
    get_seller_crm_dashboard,
    get_seller_crm_analytics,
    get_seller_crm_car_detail,
    get_seller_crm_content_summary,
    get_seller_crm_lead_detail,
    get_seller_crm_offer_detail,
    get_seller_crm_public_profile,
    get_seller_crm_marketplace_summary,
    get_seller_crm_settings_summary,
    seller_has_crm_lead_access,
    list_seller_crm_cars,
    list_seller_crm_cars_inventory,
    list_seller_crm_marketplace_activity,
    list_seller_crm_marketplace_leads,
    list_seller_crm_marketplace_requests,
    list_seller_crm_offers,
    list_seller_crm_leads,
    list_seller_crm_services,
    list_seller_crm_services_inventory,
    list_seller_crm_sources,
    seller_crm_car_supports_is_catalog,
    set_seller_crm_car_status,
    update_seller_crm_car,
)
from bot.database.repositories.seller_lead_repo import (
    cancel_seller_lead_notifications,
    mark_seller_lead_action,
    reopen_seller_lead_action,
)
from bot.database.repositories.service_repo import (
    create_seller_service,
    create_service,
    delete_service_by_seller,
    get_seller_service_detail,
    get_service_by_seller,
    get_services_by_seller,
    toggle_seller_service_status,
    update_seller_service,
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
from bot.services.seller_offer_service import submit_seller_offer_from_crm
from bot.services.site_config import get_theme_presets, merge_with_default
from bot.services.storage import upload_image

router = APIRouter(prefix="/crm/seller")
templates = Jinja2Templates(directory="bot/api/templates")
SELLER_CRM_COOKIE = "seller_crm_session"
logger = logging.getLogger(__name__)


LEAD_STATUS_TABS = [
    {"key": "new", "label": "Нові", "empty": "Нових заявок поки немає."},
    {"key": "in_work", "label": "В роботі", "empty": "Немає заявок у роботі."},
    {"key": "replied", "label": "Відповіли", "empty": "Ви ще не надіслали пропозиції."},
    {"key": "selected", "label": "Обрані", "empty": "Покупці ще не обрали ваші пропозиції."},
    {"key": "declined", "label": "Відхилені", "empty": "Відхилених заявок немає."},
    {"key": "skipped", "label": "Пропущені", "empty": "Пропущених заявок немає."},
]
ALLOWED_LEAD_STATUSES = {tab["key"] for tab in LEAD_STATUS_TABS}

OFFER_STATUS_TABS = [
    {"key": "active", "label": "Активні", "empty": "Активних пропозицій поки немає."},
    {"key": "selected", "label": "Обрані покупцем", "empty": "Покупці ще не обрали ваші пропозиції."},
    {"key": "rejected", "label": "Не обрані", "empty": "Немає відхилених пропозицій."},
    {"key": "all", "label": "Архів / всі", "empty": "Пропозицій ще немає."},
]
ALLOWED_OFFER_STATUSES = {tab["key"] for tab in OFFER_STATUS_TABS}

MODULE_KEYS = [
    ("hero", "Перший екран"),
    ("services", "Послуги"),
    ("cars", "Авто"),
    ("gallery", "Галерея"),
    ("works", "Наші роботи"),
    ("pricing", "Ціни"),
    ("contacts", "Контакти"),
    ("map", "Карта"),
    ("cta", "Заклик до дії"),
    ("reviews", "Відгуки"),
    ("footer", "Футер"),
]


def _seller_crm_context(request: Request, **kwargs):
    context = {"request": request, "title": "CRM продавця"}
    context.update(kwargs)
    return context


def _append_query(url: str, values: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: value for key, value in values.items() if value})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _safe_crm_redirect_url(request: Request, crm_slug: str, fallback: str, next_url: str = "") -> str:
    next_url = str(next_url or "") or request.headers.get("referer", "")
    if next_url:
        try:
            parts = urlsplit(next_url)
        except ValueError:
            parts = None
        if parts and not parts.scheme and not parts.netloc and parts.path.startswith(f"/crm/seller/{crm_slug}"):
            return next_url
        if parts and str(request.base_url).startswith(f"{parts.scheme}://{parts.netloc}") and parts.path.startswith(f"/crm/seller/{crm_slug}"):
            return urlunsplit(("", "", parts.path, parts.query, parts.fragment))
    return fallback


def _lead_action_notice(action: str) -> str:
    return {
        "viewed": "Заявку позначено переглянутою.",
        "declined": "Заявку відхилено локально для вашого CRM.",
        "skipped": "Заявку пропущено локально для вашого CRM.",
        "reopened": "Заявку повернуто в роботу.",
    }.get(action, "Дію виконано.")


def _parse_service_price(value: str | None) -> tuple[int | None, str | None]:
    raw = (value or "").strip().replace(" ", "")
    if not raw:
        return None, None
    if not raw.isdigit():
        return None, "Ціна має бути цілим додатним числом."
    price = int(raw)
    if price > 100_000_000:
        return None, "Ціна занадто велика."
    return price, None


def _validate_service_form(title: str, description: str, price: str) -> tuple[int | None, str | None]:
    if not (title or "").strip():
        return None, "Назва послуги обов’язкова."
    if len((description or "").strip()) > 2000:
        return None, "Опис має бути до 2000 символів."
    return _parse_service_price(price)



def _car_form_payload(description: str = "", status: str = "active", is_catalog: bool = False) -> dict[str, Any]:
    normalized_status = str(status or "active").strip().lower()
    if normalized_status in {"1", "active", "enabled", "published", "true"}:
        normalized_status = "active"
    elif normalized_status in {"0", "inactive", "disabled", "archived", "false"}:
        normalized_status = "inactive"
    return {
        "description": (description or "").strip(),
        "status": normalized_status,
        "is_catalog": bool(is_catalog),
    }


def _validate_car_form(description: str) -> str | None:
    if len((description or "").strip()) > 2000:
        return "Опис має бути до 2000 символів."
    return None


def _parse_optional_int(value: str | None) -> int | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _car_create_form_payload(
    *,
    brand: str = "",
    model: str = "",
    description: str = "",
    is_catalog: bool = False,
) -> dict[str, Any]:
    payload = _car_form_payload(description=description, status="active", is_catalog=is_catalog)
    payload.update({"brand": (brand or "").strip(), "model": (model or "").strip()})
    return payload


async def _render_car_create_form(
    request: Request,
    *,
    account,
    subscription,
    crm_slug: str,
    form: dict[str, Any] | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    brands = await get_brands_with_ids()
    models = await get_models_with_brand_ids()
    return templates.TemplateResponse(
        "seller_crm/car_form.html",
        _seller_crm_context(
            request,
            title="Додати авто — CRM продавця CarPot",
            demo_mode=False,
            current_page="content_cars",
            account=account,
            subscription=subscription,
            form_title="Додати авто",
            create_mode=True,
            car={"has_is_catalog": await seller_crm_car_supports_is_catalog()},
            form=form or _car_create_form_payload(),
            brands=brands,
            models=models,
            error=error,
            action_url=f"/crm/seller/{crm_slug}/content/cars/create",
            cancel_url=f"/crm/seller/{crm_slug}/content/cars",
            has_website=False,
            has_cars=True,
            has_services=False,
        ),
        status_code=status_code,
    )


def _service_form_payload(
    *,
    title: str = "",
    category: str = "",
    description: str = "",
    price: str = "",
) -> dict[str, str]:
    return {
        "title": (title or "").strip(),
        "category": (category or "").strip(),
        "description": (description or "").strip(),
        "price": (price or "").strip(),
    }


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

    return session, None


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
        url=f"/crm/seller/{crm_slug}/website?status={status}#{section}",
        status_code=303,
    )


def _as_config(site) -> dict[str, Any]:
    raw = site.get("config_draft") or site.get("config_live") or {}
    return merge_with_default(raw if isinstance(raw, dict) else {})


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "<1 хв"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} хв"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} год"
    days = hours // 24
    return f"{days} дн"


def _request_title(row) -> str:
    parts = [row.get("brand"), row.get("model")]
    title = " ".join(str(part).strip() for part in parts if part)
    return title or row.get("category") or row.get("request_type") or "Marketplace заявка"


def _request_status_label(row) -> str:
    offer_status = row.get("offer_status")
    action = row.get("seller_action")
    if offer_status == "accepted":
        return "Обрано покупцем"
    if offer_status == "pending":
        return "Пропозиція надіслана"
    if offer_status == "rejected":
        return "Не обрано"
    if action == "declined":
        return "Відхилено"
    if action == "skipped":
        return "Пропущено"
    if action == "viewed":
        return "Переглянуто"
    return "Очікує відповіді"


def _activity_label(row) -> str:
    action = row.get("action")
    status = row.get("status")
    labels = {
        "buyer_request_created": "Нова заявка для вас",
        "buyer_offer_created": "Пропозицію надіслано покупцю",
        "buyer_offer_accepted": "Покупець обрав вашу пропозицію",
        "viewed": "Заявку переглянуто",
        "offered": "Ви відповіли на заявку",
        "declined": "Заявку відхилено",
        "skipped": "Заявку пропущено",
    }
    label = labels.get(action, "Оновлення заявки")
    if row.get("source") == "notification" and status:
        status_labels = {"sent": "сповіщення доставлено", "pending": "сповіщення очікує", "failed": "сповіщення не доставлено", "cancelled": "сповіщення скасовано"}
        label = f"{label} · {status_labels.get(status, status)}"
    return label


def _prepare_marketplace_requests(rows) -> list[dict[str, Any]]:
    prepared = []
    for row in rows or []:
        item = dict(row)
        item["title"] = _request_title(item)
        item["short_description"] = item.get("description") or item.get("message") or "Покупець не додав опис"
        item["status_label"] = _request_status_label(item)
        prepared.append(item)
    return prepared


def _format_price(value) -> str:
    if value is None:
        return "—"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if amount.is_integer():
        return f"{int(amount):,}".replace(",", " ")
    return f"{amount:,.2f}".replace(",", " ")


def _lead_status_meta(status: str | None) -> dict[str, str]:
    mapping = {
        "selected": {"label": "Обрано", "class": "status-success"},
        "declined": {"label": "Відхилено", "class": "status-rejected"},
        "skipped": {"label": "Пропущено", "class": "status-rejected"},
        "replied": {"label": "Відповіли", "class": "status-replied"},
        "in_work": {"label": "В роботі", "class": "status-viewed"},
        "new": {"label": "Нова", "class": "status-new"},
    }
    return mapping.get(status or "new", mapping["new"])


def _offer_status_meta(status: str | None) -> dict[str, str]:
    mapping = {
        "accepted": {"label": "selected", "class": "status-success"},
        "selected": {"label": "selected", "class": "status-success"},
        "rejected": {"label": "rejected", "class": "status-rejected"},
        "pending": {"label": "pending", "class": "status-waiting"},
    }
    return mapping.get(status or "", {"label": status or "—", "class": ""})


def _prepare_marketplace_leads(rows) -> list[dict[str, Any]]:
    prepared = []
    for row in rows or []:
        item = dict(row)
        item["title"] = item.get("title") or _request_title(item)
        item["short_description"] = item.get("description") or "Покупець не додав опис"
        status_meta = _lead_status_meta(item.get("seller_status"))
        item["status_label"] = status_meta["label"]
        item["status_class"] = status_meta["class"]
        match_reasons = item.get("match_reasons")
        if isinstance(match_reasons, str):
            item["match_reasons_label"] = match_reasons
        elif match_reasons:
            item["match_reasons_label"] = ", ".join(str(reason) for reason in match_reasons)
        else:
            item["match_reasons_label"] = None
        status = item.get("seller_status")
        item["can_mark_viewed"] = status == "new" and not item.get("has_viewed")
        item["can_decline"] = status not in {"declined", "skipped", "selected"}
        item["can_skip"] = status not in {"declined", "skipped", "selected"}
        prepared.append(item)
    return prepared


def _prepare_lead_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if not detail:
        return None
    prepared = {**detail}
    request_data = {**prepared.get("request", {})}
    seller_state = {**prepared.get("seller_state", {})}
    offer = prepared.get("offer")
    marketplace = {**prepared.get("marketplace", {})}

    request_data["title"] = request_data.get("title") or _request_title(request_data)
    request_data["description"] = request_data.get("description") or "Покупець не додав детальний опис."
    match_reasons = request_data.get("match_reasons") or []
    request_data["match_reasons_label"] = ", ".join(str(reason) for reason in match_reasons) if match_reasons else None

    status_meta = _lead_status_meta(seller_state.get("seller_status"))
    seller_state["status_label"] = status_meta["label"]
    seller_state["status_class"] = status_meta["class"]

    if offer:
        offer = {**offer}
        offer_meta = _offer_status_meta(offer.get("status"))
        offer["status_label"] = offer_meta["label"]
        offer["status_class"] = offer_meta["class"]
        offer["price_label"] = _format_price(offer.get("price"))
        offer["price_input"] = "" if offer.get("price") is None else str(offer.get("price"))

    marketplace["state_label"] = "Обрано покупцем" if marketplace.get("is_selected") else "Очікує рішення покупця"
    marketplace["state_class"] = "status-success" if marketplace.get("is_selected") else "status-waiting"

    seller_status = seller_state.get("seller_status")
    prepared["can_mark_viewed"] = not seller_state.get("has_viewed")
    prepared["can_decline"] = seller_status not in {"declined", "skipped", "selected"}
    prepared["can_skip"] = seller_status not in {"declined", "skipped", "selected"}
    prepared["can_reopen"] = seller_status in {"declined", "skipped"}
    prepared["may_respond"] = not marketplace.get("selected_other_seller") and (
        bool(offer) or seller_status not in {"declined", "skipped"}
    )
    if marketplace.get("selected_other_seller"):
        prepared["response_block_reason"] = "Покупець уже обрав іншого продавця."
    elif seller_status in {"declined", "skipped"} and not offer:
        prepared["response_block_reason"] = "Цю заявку вже відхилено або пропущено."
    else:
        prepared["response_block_reason"] = None

    prepared["request"] = request_data
    prepared["seller_state"] = seller_state
    prepared["offer"] = offer
    prepared["marketplace"] = marketplace
    prepared["timeline"] = prepared.get("timeline") or []
    return prepared


def _offer_workspace_status_meta(offer: dict[str, Any]) -> dict[str, str]:
    if offer.get("is_selected"):
        return {"label": "Обрано покупцем", "class": "status-success", "state": "selected"}
    if offer.get("offer_status") == "rejected" or offer.get("status") == "rejected":
        return {"label": "Не обрано", "class": "status-rejected", "state": "rejected"}
    if offer.get("offer_status") == "accepted" or offer.get("status") == "accepted":
        return {"label": "Обрано покупцем", "class": "status-success", "state": "selected"}
    return {"label": "Очікує рішення", "class": "status-waiting", "state": "waiting"}


def _prepare_offer_cards(rows) -> list[dict[str, Any]]:
    prepared = []
    for row in rows or []:
        item = dict(row)
        item["request_title"] = item.get("request_title") or _request_title(item)
        item["request_description_short"] = item.get("request_description_short") or "Покупець не додав опис."
        item["price_label"] = _format_price(item.get("price_offer"))
        status_meta = _offer_workspace_status_meta(item)
        item["status_label"] = status_meta["label"]
        item["status_class"] = status_meta["class"]
        item["selection_state"] = status_meta["state"]
        prepared.append(item)
    return prepared


def _prepare_offer_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if not detail:
        return None
    prepared = {**detail}
    offer = {**prepared.get("offer", {})}
    request_data = {**prepared.get("request", {})}
    selection = {**prepared.get("selection", {})}

    request_data["title"] = request_data.get("title") or _request_title(request_data)
    request_data["description"] = request_data.get("description") or "Покупець не додав детальний опис."
    offer["price_label"] = _format_price(offer.get("price"))

    status_meta = _offer_workspace_status_meta({
        "status": offer.get("status"),
        "is_selected": selection.get("is_selected"),
    })
    offer["status_label"] = status_meta["label"]
    offer["status_class"] = status_meta["class"]
    selection["state"] = status_meta["state"]
    selection["state_label"] = status_meta["label"]
    selection["state_class"] = status_meta["class"]

    prepared["offer"] = offer
    prepared["request"] = request_data
    prepared["selection"] = selection
    prepared["timeline"] = prepared.get("timeline") or []
    return prepared


def _prepare_activity(rows) -> list[dict[str, Any]]:
    prepared = []
    for row in rows or []:
        item = dict(row)
        item["label"] = _activity_label(item)
        item["title"] = _request_title(item)
        prepared.append(item)
    return prepared


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
        media.append({"type": "Лого", "url": logo, "title": "Лого у шапці"})
    for url in config.get("hero", {}).get("banners", []):
        media.append({"type": "Банер", "url": url, "title": "Банер першого екрана"})
    for image in config.get("gallery", {}).get("images", []):
        url = image.get("url") if isinstance(image, dict) else image
        if url:
            media.append({"type": "Галерея", "url": url, "title": image.get("title", "Галерея") if isinstance(image, dict) else "Галерея"})
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
            current_page="dashboard",
            account={"crm_slug": "demo", "shop_name": "Demo Auto Hub"},
            subscription={"expires_at": datetime.utcnow() + timedelta(days=30)},
            stats=demo_stats,
            marketplace_summary={"new_requests": 3, "waiting_response": 2, "accepted_offers": 1, "avg_response_label": "18 хв"},
            marketplace_requests=[],
            marketplace_activity=[],
            leads=demo_leads,
            cars=[],
            services=[],
            sources=[{"source": "telegram", "visits": 93}, {"source": "google", "visits": 71}, {"source": "direct", "visits": 22}],
            has_website=True,
            has_cars=False,
            has_services=True,
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

    if not verify_crm_password(password, account["password_hash"]):
        return templates.TemplateResponse(
            "seller_crm/login.html",
            _seller_crm_context(request, error=login_error, identifier=identifier, slug=slug),
            status_code=401,
        )

    token = secrets.token_urlsafe(32)
    await create_crm_session(account["id"], token, datetime.utcnow() + timedelta(days=SELLER_CRM_SESSION_DAYS))
    logger.info(
        "CRM_LOGIN_SUCCESS seller_id=%s account_id=%s slug=%s",
        account["seller_id"],
        account["id"],
        account["crm_slug"],
    )

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


@router.get("/{crm_slug}/leads")
async def seller_crm_marketplace_leads(
    request: Request,
    crm_slug: str,
    status: str = "new",
    action_status: str | None = None,
    action_error: str | None = None,
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    active_status = status if status in ALLOWED_LEAD_STATUSES else "new"
    tabs = [
        {
            **tab,
            "active": tab["key"] == active_status,
            "href": f"/crm/seller/{crm_slug}/leads?status={tab['key']}",
        }
        for tab in LEAD_STATUS_TABS
    ]
    active_tab = next(tab for tab in tabs if tab["active"])
    leads = _prepare_marketplace_leads(
        await list_seller_crm_marketplace_leads(
            account["seller_id"],
            status=active_status,
        )
    )

    return templates.TemplateResponse(
        "seller_crm/leads.html",
        _seller_crm_context(
            request,
            title="Marketplace заявки — CRM продавця CarPot",
            demo_mode=False,
            current_page="leads",
            account=account,
            subscription=subscription,
            leads=leads,
            lead_tabs=tabs,
            active_status=active_status,
            empty_message=active_tab["empty"],
            action_status=action_status,
            action_error=action_error,
        ),
    )


@router.get("/{crm_slug}/leads/{request_id}")
async def seller_crm_lead_detail(
    request: Request,
    crm_slug: str,
    request_id: str,
    offer_status: str | None = None,
    error: str | None = None,
    action_status: str | None = None,
    action_error: str | None = None,
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    try:
        parsed_request_id = int(request_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Lead not found") from exc

    lead_detail = _prepare_lead_detail(
        await get_seller_crm_lead_detail(
            account["seller_id"],
            parsed_request_id,
        )
    )
    if not lead_detail:
        raise HTTPException(status_code=404, detail="Lead not found")

    return templates.TemplateResponse(
        "seller_crm/lead_detail.html",
        _seller_crm_context(
            request,
            title=f"Заявка #{parsed_request_id} — CRM продавця CarPot",
            demo_mode=False,
            current_page="leads",
            account=account,
            subscription=subscription,
            lead=lead_detail,
            offer_status=offer_status,
            error=error,
            action_status=action_status,
            action_error=action_error,
        ),
    )


async def _handle_seller_crm_lead_action(
    request: Request,
    crm_slug: str,
    request_id: str,
    action: str,
    next_url: str = "",
):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    try:
        parsed_request_id = int(request_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Lead not found")

    fallback_url = f"/crm/seller/{crm_slug}/leads/{parsed_request_id}"
    redirect_url = _safe_crm_redirect_url(request, crm_slug, fallback_url, next_url)
    seller_id = int(account["seller_id"])

    try:
        has_access = await seller_has_crm_lead_access(seller_id, parsed_request_id)
        if not has_access:
            logger.warning(
                "Blocked CRM seller lead action for inaccessible request seller_id=%s request_id=%s action=%s",
                seller_id,
                parsed_request_id,
                action,
            )
            return RedirectResponse(
                url=_append_query(redirect_url, {"action_error": "Заявку не знайдено або вона недоступна."}),
                status_code=303,
            )

        if action == "reopened":
            await reopen_seller_lead_action(seller_id=seller_id, request_id=parsed_request_id)
        else:
            repository_action = {"viewed": "viewed", "declined": "declined", "skipped": "skipped"}.get(action)
            if not repository_action:
                raise ValueError("Invalid CRM lead action")
            await mark_seller_lead_action(
                seller_id=seller_id,
                request_id=parsed_request_id,
                action=repository_action,
                metadata={"source": "seller_crm"},
            )
            if repository_action == "declined":
                await cancel_seller_lead_notifications(seller_id=seller_id, request_id=parsed_request_id)

        logger.info(
            "CRM seller lead action completed seller_id=%s request_id=%s action=%s",
            seller_id,
            parsed_request_id,
            action,
        )
        return RedirectResponse(
            url=_append_query(redirect_url, {"action_status": _lead_action_notice(action)}),
            status_code=303,
        )
    except Exception:
        logger.exception(
            "CRM seller lead action failed seller_id=%s request_id=%s action=%s",
            seller_id,
            parsed_request_id,
            action,
        )
        return RedirectResponse(
            url=_append_query(redirect_url, {"action_error": "Не вдалося виконати дію. Спробуйте ще раз."}),
            status_code=303,
        )


@router.post("/{crm_slug}/leads/{request_id}/view")
async def seller_crm_mark_lead_viewed(
    request: Request,
    crm_slug: str,
    request_id: str,
    next_url: str = Form(""),
):
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, "viewed", next_url)


@router.post("/{crm_slug}/leads/{request_id}/decline")
async def seller_crm_decline_lead(
    request: Request,
    crm_slug: str,
    request_id: str,
    next_url: str = Form(""),
):
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, "declined", next_url)


@router.post("/{crm_slug}/leads/{request_id}/skip")
async def seller_crm_skip_lead(
    request: Request,
    crm_slug: str,
    request_id: str,
    next_url: str = Form(""),
):
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, "skipped", next_url)


@router.post("/{crm_slug}/leads/{request_id}/reopen")
async def seller_crm_reopen_lead(
    request: Request,
    crm_slug: str,
    request_id: str,
    next_url: str = Form(""),
):
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, "reopened", next_url)


@router.post("/{crm_slug}/leads/{request_id}/offer")
async def seller_crm_submit_offer(
    request: Request,
    crm_slug: str,
    request_id: str,
    price_text: str = Form(""),
    message: str = Form(""),
):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    try:
        parsed_request_id = int(request_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Lead not found")

    redirect_base = f"/crm/seller/{crm_slug}/leads/{parsed_request_id}"
    try:
        result = await submit_seller_offer_from_crm(
            seller_id=int(account["seller_id"]),
            request_id=parsed_request_id,
            price_text=price_text,
            message=message,
        )
    except Exception:
        logger.exception(
            "CRM seller offer submit failed seller_id=%s request_id=%s",
            account.get("seller_id"),
            parsed_request_id,
        )
        query = urlencode({"error": "Не вдалося надіслати пропозицію. Спробуйте ще раз."})
        return RedirectResponse(url=f"{redirect_base}?{query}", status_code=303)

    if not result.get("ok"):
        query = urlencode({"error": result.get("error") or "Перевірте дані пропозиції."})
        return RedirectResponse(url=f"{redirect_base}?{query}", status_code=303)

    notification_status = result.get("notification_status")
    if notification_status == "already_recorded":
        status = "updated"
    elif notification_status == "sent":
        status = "sent"
    else:
        status = "saved"
    query = urlencode({"offer_status": status})
    return RedirectResponse(url=f"{redirect_base}?{query}", status_code=303)


@router.get("/{crm_slug}/offers")
async def seller_crm_offers(request: Request, crm_slug: str, status: str = "active"):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    active_status = status if status in ALLOWED_OFFER_STATUSES else "active"
    tabs = [
        {
            **tab,
            "active": tab["key"] == active_status,
            "href": f"/crm/seller/{crm_slug}/offers?status={tab['key']}",
        }
        for tab in OFFER_STATUS_TABS
    ]
    active_tab = next(tab for tab in tabs if tab["active"])
    offers = _prepare_offer_cards(
        await list_seller_crm_offers(
            account["seller_id"],
            status=active_status,
        )
    )

    return templates.TemplateResponse(
        "seller_crm/offers.html",
        _seller_crm_context(
            request,
            title="Пропозиції — CRM продавця CarPot",
            demo_mode=False,
            current_page="offers",
            account=account,
            subscription=subscription,
            offers=offers,
            offer_tabs=tabs,
            active_status=active_status,
            empty_message=active_tab["empty"],
        ),
    )


@router.get("/{crm_slug}/offers/{offer_id}")
async def seller_crm_offer_detail(request: Request, crm_slug: str, offer_id: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    try:
        parsed_offer_id = int(offer_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Offer not found") from exc

    offer_detail = _prepare_offer_detail(
        await get_seller_crm_offer_detail(
            account["seller_id"],
            parsed_offer_id,
        )
    )
    if not offer_detail:
        raise HTTPException(status_code=404, detail="Offer not found")

    return templates.TemplateResponse(
        "seller_crm/offer_detail.html",
        _seller_crm_context(
            request,
            title=f"Пропозиція #{parsed_offer_id} — CRM продавця CarPot",
            demo_mode=False,
            current_page="offers",
            account=account,
            subscription=subscription,
            offer_detail=offer_detail,
        ),
    )


@router.get("/{crm_slug}/content")
async def seller_crm_content(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    summary = dict(await get_seller_crm_content_summary(seller_id) or {})
    site = await get_site_by_seller(seller_id)
    account_flags = dict(account)
    has_website = bool(site or account_flags.get("has_site") or account_flags.get("website"))
    has_cars = int(summary.get("active_cars") or 0) > 0
    has_services = int(summary.get("active_services") or 0) > 0

    priority_sections = [
        {"key": "cars", "label": "Авто на розборі", "href": f"/crm/seller/{crm_slug}/content/cars"},
        {"key": "services", "label": "Послуги", "href": f"/crm/seller/{crm_slug}/content/services"},
        {"key": "parts", "label": "Товари / Запчастини", "href": f"/crm/seller/{crm_slug}/content"},
    ]
    if has_services and not has_cars:
        priority_sections = [priority_sections[1], priority_sections[0], priority_sections[2]]

    return templates.TemplateResponse(
        "seller_crm/content.html",
        _seller_crm_context(
            request,
            title="Мій контент — CRM продавця CarPot",
            demo_mode=False,
            current_page="content",
            account=account,
            subscription=subscription,
            summary=summary,
            priority_sections=priority_sections,
            has_website=has_website,
            has_cars=has_cars,
            has_services=has_services,
        ),
    )


@router.get("/{crm_slug}/content/services")
async def seller_crm_content_services(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    summary = dict(await get_seller_crm_content_summary(seller_id) or {})
    services = [dict(service) for service in await list_seller_crm_services_inventory(seller_id)]
    for service in services:
        detail = await get_seller_service_detail(seller_id=seller_id, service_id=service["service_id"])
        if detail:
            service["is_active"] = detail.get("is_active", True)
            service["status_supported"] = detail.get("status_supported", False)
            service["content_completeness"] = detail.get("content_completeness", 0)
        else:
            service["is_active"] = True
            service["status_supported"] = False
            service["content_completeness"] = 0
        photo_id = service.get("photo_id") or ""
        service["photo_is_url"] = isinstance(photo_id, str) and photo_id.startswith(("http://", "https://"))
    totals = {
        "views": sum(int(service.get("views") or 0) for service in services),
        "calls": sum(int(service.get("calls") or 0) for service in services),
        "clicks": sum(int(service.get("clicks") or 0) for service in services),
        "without_description": sum(1 for service in services if not service.get("has_description")),
        "without_price": sum(1 for service in services if not service.get("has_price")),
        "without_photo": sum(1 for service in services if not service.get("has_photo")),
    }
    site = await get_site_by_seller(seller_id)
    account_flags = dict(account)
    has_website = bool(site or account_flags.get("has_site") or account_flags.get("website"))

    return templates.TemplateResponse(
        "seller_crm/content_services.html",
        _seller_crm_context(
            request,
            title="Послуги — CRM продавця CarPot",
            demo_mode=False,
            current_page="content_services",
            account=account,
            subscription=subscription,
            summary=summary,
            services=services,
            totals=totals,
            has_website=has_website,
            has_cars=int(summary.get("active_cars") or 0) > 0,
            has_services=bool(services),
        ),
    )


@router.get("/{crm_slug}/content/services/create")
async def seller_crm_service_create_form(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    return templates.TemplateResponse(
        "seller_crm/service_form.html",
        _seller_crm_context(
            request,
            title="Додати послугу — CRM продавця CarPot",
            demo_mode=False,
            current_page="content_services",
            account=account,
            subscription=subscription,
            form_title="Додати послугу",
            service=None,
            form=_service_form_payload(),
            error=None,
            action_url=f"/crm/seller/{crm_slug}/content/services/create",
            cancel_url=f"/crm/seller/{crm_slug}/content/services",
            has_website=False,
            has_cars=False,
            has_services=True,
        ),
    )


@router.post("/{crm_slug}/content/services/create")
async def seller_crm_service_create(
    request: Request,
    crm_slug: str,
    title: str = Form(""),
    category: str = Form(""),
    description: str = Form(""),
    price: str = Form(""),
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    parsed_price, error = _validate_service_form(title, description, price)
    form = _service_form_payload(title=title, category=category, description=description, price=price)
    if error:
        return templates.TemplateResponse(
            "seller_crm/service_form.html",
            _seller_crm_context(
                request,
                title="Додати послугу — CRM продавця CarPot",
                demo_mode=False,
                current_page="content_services",
                account=account,
                subscription=subscription,
                form_title="Додати послугу",
                service=None,
                form=form,
                error=error,
                action_url=f"/crm/seller/{crm_slug}/content/services/create",
                cancel_url=f"/crm/seller/{crm_slug}/content/services",
                has_website=False,
                has_cars=False,
                has_services=True,
            ),
            status_code=400,
        )

    service_id = await create_seller_service(
        seller_id=account["seller_id"],
        title=title,
        category=category,
        description=description,
        price=parsed_price,
        city=account.get("city") or "",
        address="",
    )
    if not service_id:
        return templates.TemplateResponse(
            "seller_crm/service_form.html",
            _seller_crm_context(
                request,
                title="Додати послугу — CRM продавця CarPot",
                demo_mode=False,
                current_page="content_services",
                account=account,
                subscription=subscription,
                form_title="Додати послугу",
                service=None,
                form=form,
                error="Не вдалося створити послугу. Перевірте поля й спробуйте ще раз.",
                action_url=f"/crm/seller/{crm_slug}/content/services/create",
                cancel_url=f"/crm/seller/{crm_slug}/content/services",
                has_website=False,
                has_cars=False,
                has_services=True,
            ),
            status_code=400,
        )

    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/services/{service_id}?status=created", status_code=303)


@router.get("/{crm_slug}/content/services/{service_id}/edit")
async def seller_crm_service_edit_form(request: Request, crm_slug: str, service_id: int):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    service = await get_seller_service_detail(seller_id=account["seller_id"], service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    return templates.TemplateResponse(
        "seller_crm/service_form.html",
        _seller_crm_context(
            request,
            title="Редагувати послугу — CRM продавця CarPot",
            demo_mode=False,
            current_page="content_services",
            account=account,
            subscription=subscription,
            form_title="Редагувати послугу",
            service=service,
            form=_service_form_payload(
                title=service.get("title"),
                category=service.get("category"),
                description=service.get("description"),
                price="" if service.get("price") is None else str(service.get("price")),
            ),
            error=None,
            action_url=f"/crm/seller/{crm_slug}/content/services/{service_id}/edit",
            cancel_url=f"/crm/seller/{crm_slug}/content/services/{service_id}",
            has_website=False,
            has_cars=False,
            has_services=True,
        ),
    )


@router.post("/{crm_slug}/content/services/{service_id}/edit")
async def seller_crm_service_edit(
    request: Request,
    crm_slug: str,
    service_id: int,
    title: str = Form(""),
    category: str = Form(""),
    description: str = Form(""),
    price: str = Form(""),
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    service = await get_seller_service_detail(seller_id=account["seller_id"], service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    parsed_price, error = _validate_service_form(title, description, price)
    form = _service_form_payload(title=title, category=category, description=description, price=price)
    if error:
        return templates.TemplateResponse(
            "seller_crm/service_form.html",
            _seller_crm_context(
                request,
                title="Редагувати послугу — CRM продавця CarPot",
                demo_mode=False,
                current_page="content_services",
                account=account,
                subscription=subscription,
                form_title="Редагувати послугу",
                service=service,
                form=form,
                error=error,
                action_url=f"/crm/seller/{crm_slug}/content/services/{service_id}/edit",
                cancel_url=f"/crm/seller/{crm_slug}/content/services/{service_id}",
                has_website=False,
                has_cars=False,
                has_services=True,
            ),
            status_code=400,
        )

    saved = await update_seller_service(
        seller_id=account["seller_id"],
        service_id=service_id,
        title=title,
        category=category,
        description=description,
        price=parsed_price,
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Service not found")

    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/services/{service_id}?status=updated", status_code=303)


@router.get("/{crm_slug}/content/services/{service_id}")
async def seller_crm_service_detail(request: Request, crm_slug: str, service_id: int, status: str | None = None, error: str | None = None):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    service = await get_seller_service_detail(seller_id=account["seller_id"], service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    return templates.TemplateResponse(
        "seller_crm/service_detail.html",
        _seller_crm_context(
            request,
            title=f"{service.get('title') or 'Послуга'} — CRM продавця CarPot",
            demo_mode=False,
            current_page="content_services",
            account=account,
            subscription=subscription,
            service=service,
            status=status,
            error=error,
            has_website=False,
            has_cars=False,
            has_services=True,
        ),
    )


async def _toggle_crm_service(request: Request, crm_slug: str, service_id: int, is_active: bool):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    service = await get_seller_service_detail(seller_id=account["seller_id"], service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    toggled = await toggle_seller_service_status(
        seller_id=account["seller_id"],
        service_id=service_id,
        is_active=is_active,
    )
    query_key = "status" if toggled else "error"
    query_value = "enabled" if is_active else "disabled"
    if not toggled:
        query_value = "status_not_supported"
    return RedirectResponse(
        url=f"/crm/seller/{crm_slug}/content/services/{service_id}?{query_key}={query_value}",
        status_code=303,
    )


@router.post("/{crm_slug}/content/services/{service_id}/enable")
async def seller_crm_service_enable(request: Request, crm_slug: str, service_id: int):
    return await _toggle_crm_service(request, crm_slug, service_id, True)


@router.post("/{crm_slug}/content/services/{service_id}/disable")
async def seller_crm_service_disable(request: Request, crm_slug: str, service_id: int):
    return await _toggle_crm_service(request, crm_slug, service_id, False)


@router.get("/{crm_slug}/content/cars/create")
async def seller_crm_car_create_form(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    return await _render_car_create_form(
        request,
        account=account,
        subscription=subscription,
        crm_slug=crm_slug,
    )


@router.post("/{crm_slug}/content/cars/create")
async def seller_crm_car_create(
    request: Request,
    crm_slug: str,
    brand: str = Form(""),
    model: str = Form(""),
    description: str = Form(""),
    is_catalog: str | None = Form(None),
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    catalog_value = is_catalog in {"1", "true", "on", "yes"}
    form = _car_create_form_payload(
        brand=brand,
        model=model,
        description=description,
        is_catalog=catalog_value,
    )
    error = _validate_car_form(description)
    if error:
        return await _render_car_create_form(
            request,
            account=account,
            subscription=subscription,
            crm_slug=crm_slug,
            form=form,
            error=error,
            status_code=400,
        )

    brand_id = _parse_optional_int(brand)
    model_id = _parse_optional_int(model)
    existing_model_id = (
        await get_existing_model_id_by_brand_model_ids(brand_id, model_id)
        if brand_id and model_id
        else None
    )
    if not existing_model_id:
        return await _render_car_create_form(
            request,
            account=account,
            subscription=subscription,
            crm_slug=crm_slug,
            form=form,
            error="Марку або модель не знайдено. Додайте авто через Telegram-бот або зверніться в підтримку.",
            status_code=400,
        )

    try:
        created = await create_seller_crm_car(
            seller_id=account["seller_id"],
            model_id=existing_model_id,
            description=description,
            is_catalog=catalog_value,
        )
    except SellerCrmGarageFullError:
        return await _render_car_create_form(
            request,
            account=account,
            subscription=subscription,
            crm_slug=crm_slug,
            form=form,
            error="Немає вільних місць у гаражі.",
            status_code=400,
        )

    if not created:
        return await _render_car_create_form(
            request,
            account=account,
            subscription=subscription,
            crm_slug=crm_slug,
            form=form,
            error="Не вдалося створити авто. Спробуйте ще раз або зверніться в підтримку.",
            status_code=400,
        )

    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars", status_code=303)


@router.get("/{crm_slug}/content/cars/{car_id}/edit")
async def seller_crm_car_edit_form(request: Request, crm_slug: str, car_id: int):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    car = await get_seller_crm_car_detail(account["seller_id"], car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")

    return templates.TemplateResponse(
        "seller_crm/car_form.html",
        _seller_crm_context(
            request,
            title="Редагувати авто — CRM продавця CarPot",
            demo_mode=False,
            current_page="content_cars",
            account=account,
            subscription=subscription,
            form_title="Редагувати авто",
            car=car,
            form=_car_form_payload(
                description=car.get("description") or "",
                status=car.get("status_label") or "active",
                is_catalog=bool(car.get("is_catalog")),
            ),
            error=None,
            action_url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/edit",
            cancel_url=f"/crm/seller/{crm_slug}/content/cars/{car_id}",
            has_website=False,
            has_cars=True,
            has_services=False,
        ),
    )


@router.post("/{crm_slug}/content/cars/{car_id}/edit")
async def seller_crm_car_edit(
    request: Request,
    crm_slug: str,
    car_id: int,
    description: str = Form(""),
    status: str = Form("active"),
    is_catalog: str | None = Form(None),
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    car = await get_seller_crm_car_detail(account["seller_id"], car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")

    normalized_status = _car_form_payload(status=status)["status"]
    catalog_value = is_catalog in {"1", "true", "on", "yes"}
    error = _validate_car_form(description)
    if error:
        return templates.TemplateResponse(
            "seller_crm/car_form.html",
            _seller_crm_context(
                request,
                title="Редагувати авто — CRM продавця CarPot",
                demo_mode=False,
                current_page="content_cars",
                account=account,
                subscription=subscription,
                form_title="Редагувати авто",
                car=car,
                form=_car_form_payload(description=description, status=normalized_status, is_catalog=catalog_value),
                error=error,
                action_url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/edit",
                cancel_url=f"/crm/seller/{crm_slug}/content/cars/{car_id}",
                has_website=False,
                has_cars=True,
                has_services=False,
            ),
            status_code=400,
        )

    saved = await update_seller_crm_car(
        seller_id=account["seller_id"],
        car_id=car_id,
        description=description,
        status=normalized_status,
        is_catalog=catalog_value if car.get("has_is_catalog") else None,
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Car not found")

    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{car_id}?status=updated", status_code=303)


@router.get("/{crm_slug}/content/cars/{car_id}")
async def seller_crm_car_detail(request: Request, crm_slug: str, car_id: int, status: str | None = None, error: str | None = None):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    car = await get_seller_crm_car_detail(account["seller_id"], car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")

    return templates.TemplateResponse(
        "seller_crm/car_detail.html",
        _seller_crm_context(
            request,
            title=f"{car.get('brand') or 'Авто'} {car.get('model') or ''} — CRM продавця CarPot",
            demo_mode=False,
            current_page="content_cars",
            account=account,
            subscription=subscription,
            car=car,
            status=status,
            error=error,
            has_website=False,
            has_cars=True,
            has_services=False,
        ),
    )


async def _toggle_crm_car(request: Request, crm_slug: str, car_id: int, new_status: str):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    car = await get_seller_crm_car_detail(account["seller_id"], car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")

    toggled = await set_seller_crm_car_status(account["seller_id"], car_id, new_status)
    query_key = "status" if toggled else "error"
    query_value = "enabled" if new_status == "active" else "disabled"
    if not toggled:
        query_value = "status_not_supported"
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{car_id}?{query_key}={query_value}", status_code=303)


@router.post("/{crm_slug}/content/cars/{car_id}/enable")
async def seller_crm_car_enable(request: Request, crm_slug: str, car_id: int):
    return await _toggle_crm_car(request, crm_slug, car_id, "active")


@router.post("/{crm_slug}/content/cars/{car_id}/disable")
async def seller_crm_car_disable(request: Request, crm_slug: str, car_id: int):
    return await _toggle_crm_car(request, crm_slug, car_id, "inactive")


@router.get("/{crm_slug}/content/cars")
async def seller_crm_content_cars(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    summary = dict(await get_seller_crm_content_summary(seller_id) or {})
    cars = [dict(car) for car in await list_seller_crm_cars_inventory(seller_id)]
    for car in cars:
        raw_status = str(car.get("status") if car.get("status") is not None else "active").strip().lower()
        car["status_label"] = "active" if raw_status in {"1", "active", "enabled", "published", "true"} else "inactive"
        photo_id = car.get("photo_id") or ""
        car["photo_is_url"] = isinstance(photo_id, str) and photo_id.startswith(("http://", "https://"))
    totals = {
        "views": sum(int(car.get("views") or 0) for car in cars),
        "phone_clicks": sum(int(car.get("phone_clicks") or 0) for car in cars),
        "site_clicks": sum(int(car.get("site_clicks") or 0) for car in cars),
    }
    site = await get_site_by_seller(seller_id)
    account_flags = dict(account)
    has_website = bool(site or account_flags.get("has_site") or account_flags.get("website"))

    return templates.TemplateResponse(
        "seller_crm/content_cars.html",
        _seller_crm_context(
            request,
            title="Авто на розборі — CRM продавця CarPot",
            demo_mode=False,
            current_page="content_cars",
            account=account,
            subscription=subscription,
            summary=summary,
            cars=cars,
            totals=totals,
            has_website=has_website,
            has_cars=bool(cars),
            has_services=int(summary.get("active_services") or 0) > 0,
        ),
    )


@router.get("/{crm_slug}/settings")
async def seller_crm_settings(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    settings_summary = await get_seller_crm_settings_summary(seller_id)
    if not settings_summary:
        raise HTTPException(status_code=404, detail="Seller settings not found")

    has_website = bool(settings_summary.get("site") or settings_summary.get("has_site"))
    content_summary = dict(await get_seller_crm_content_summary(seller_id) or {})

    return templates.TemplateResponse(
        "seller_crm/settings.html",
        _seller_crm_context(
            request,
            title="Налаштування та тарифи — CRM продавця CarPot",
            demo_mode=False,
            current_page="settings",
            account=account,
            subscription=subscription,
            settings=settings_summary,
            has_website=has_website,
            has_cars=int(settings_summary.get("used_garage_slots") or 0) > 0,
            has_services=int(content_summary.get("active_services") or 0) > 0,
        ),
    )


@router.get("/{crm_slug}/profile")
async def seller_crm_profile(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    profile = dict(await get_seller_crm_public_profile(seller_id) or {})
    if not profile:
        raise HTTPException(status_code=404, detail="Seller profile not found")

    site = await get_site_by_seller(seller_id)
    public_site_url = build_site_url(site["subdomain"]) if site and site.get("subdomain") else None
    has_website = bool(public_site_url or profile.get("has_site") or profile.get("website"))

    response_activity = profile.get("response_activity") or {}
    if isinstance(response_activity, str):
        try:
            response_activity = json.loads(response_activity)
        except json.JSONDecodeError:
            response_activity = {}
    profile["avg_response_label"] = _format_duration(response_activity.get("avg_response_seconds"))
    photo_id = profile.get("photo_id") or ""
    profile["photo_is_url"] = isinstance(photo_id, str) and photo_id.startswith(("http://", "https://"))

    completeness_items = [
        {"label": "Назва магазину", "done": bool(profile.get("shop_name") or profile.get("name")), "missing": "Назву магазину не вказано"},
        {"label": "Телефон", "done": bool(profile.get("phone")), "missing": "Телефон не вказано"},
        {"label": "Місто", "done": bool(profile.get("city")), "missing": "Місто не вказано"},
        {"label": "Опис профілю", "done": bool(profile.get("description")), "missing": "Опис профілю не додано"},
        {"label": "Фото/логотип", "done": bool(profile.get("photo_id")), "missing": "Фото/логотип не додано"},
        {
            "label": "Авто або послуга",
            "done": int(profile.get("active_cars_count") or 0) + int(profile.get("active_services_count") or 0) > 0,
            "missing": "Додайте хоча б одне авто або послугу",
        },
        {"label": "Верифікація", "done": bool(profile.get("is_verified")), "missing": "Профіль ще не верифіковано"},
    ]
    completed_count = sum(1 for item in completeness_items if item["done"])
    completeness_percent = round((completed_count / len(completeness_items)) * 100)

    return templates.TemplateResponse(
        "seller_crm/profile.html",
        _seller_crm_context(
            request,
            title="Профіль продавця — CRM продавця CarPot",
            demo_mode=False,
            current_page="profile",
            account=account,
            subscription=subscription,
            profile=profile,
            completeness_items=completeness_items,
            completed_count=completed_count,
            completeness_percent=completeness_percent,
            public_site_url=public_site_url,
            has_website=has_website,
            has_cars=int(profile.get("active_cars_count") or 0) > 0,
            has_services=int(profile.get("active_services_count") or 0) > 0,
        ),
    )


@router.get("/{crm_slug}")
async def seller_crm_dashboard(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    account_flags = dict(account)
    stats = await get_seller_crm_dashboard(seller_id)
    marketplace_summary = dict(await get_seller_crm_marketplace_summary(seller_id) or {})
    marketplace_summary["avg_response_label"] = _format_duration(marketplace_summary.get("avg_response_seconds"))
    marketplace_requests = _prepare_marketplace_requests(await list_seller_crm_marketplace_requests(seller_id))
    marketplace_activity = _prepare_activity(await list_seller_crm_marketplace_activity(seller_id))
    leads = await list_seller_crm_leads(seller_id)
    cars = await list_seller_crm_cars(seller_id)
    services = await list_seller_crm_services(seller_id)
    sources = await list_seller_crm_sources(seller_id)
    site = await get_site_by_seller(seller_id)
    has_website = bool(site or account_flags.get("has_site") or account_flags.get("website"))
    has_cars = bool(cars)
    has_services = bool(services)

    return templates.TemplateResponse(
        "seller_crm/dashboard.html",
        _seller_crm_context(
            request,
            title="CRM продавця CarPot",
            demo_mode=False,
            current_page="dashboard",
            account=account,
            subscription=subscription,
            stats=stats or {},
            marketplace_summary=marketplace_summary,
            marketplace_requests=marketplace_requests,
            marketplace_activity=marketplace_activity,
            leads=leads,
            cars=cars,
            services=services,
            sources=sources,
            has_website=has_website,
            has_cars=has_cars,
            has_services=has_services,
        ),
    )


@router.get("/{crm_slug}/analytics")
async def seller_crm_analytics(request: Request, crm_slug: str, days: int = 30):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    normalized_days = max(1, min(int(days or 30), 365))
    seller_id = account["seller_id"]
    analytics = dict(await get_seller_crm_analytics(seller_id, normalized_days) or {})
    analytics["average_response_label"] = _format_duration(analytics.get("average_response_seconds"))

    funnel_max = max(
        int(analytics.get("routed_requests") or 0),
        int(analytics.get("viewed_requests") or 0),
        int(analytics.get("offers_sent") or 0),
        int(analytics.get("offers_selected") or 0),
        1,
    )
    analytics["funnel"] = [
        {"label": "Направлено", "value": int(analytics.get("routed_requests") or 0)},
        {"label": "Переглянуто", "value": int(analytics.get("viewed_requests") or 0)},
        {"label": "Пропозиції", "value": int(analytics.get("offers_sent") or 0)},
        {"label": "Обрано", "value": int(analytics.get("offers_selected") or 0)},
    ]
    for step in analytics["funnel"]:
        step["percent"] = max(4, round((step["value"] / funnel_max) * 100)) if step["value"] else 4

    routed_requests = max(int(analytics.get("routed_requests") or 0), 1)
    offers_sent = max(int(analytics.get("offers_sent") or 0), 1)
    analytics["declined_percent"] = min(100, round((int(analytics.get("declined_requests") or 0) / routed_requests) * 100))
    analytics["skipped_percent"] = min(100, round((int(analytics.get("skipped_requests") or 0) / routed_requests) * 100))
    analytics["rejected_percent"] = min(100, round((int(analytics.get("offers_rejected") or 0) / offers_sent) * 100))

    site = await get_site_by_seller(seller_id)
    account_flags = dict(account)
    has_website = bool(site or analytics.get("has_website") or account_flags.get("has_site") or account_flags.get("website"))
    cars = await list_seller_crm_cars(seller_id, limit=1)
    services = await list_seller_crm_services(seller_id, limit=1)

    return templates.TemplateResponse(
        "seller_crm/analytics.html",
        _seller_crm_context(
            request,
            title="Аналітика та статистика — CRM продавця",
            demo_mode=False,
            current_page="analytics",
            account=account,
            subscription=subscription,
            analytics=analytics,
            days=normalized_days,
            has_website=has_website,
            has_cars=bool(cars),
            has_services=bool(services),
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
        return templates.TemplateResponse(
            "seller_crm/website.html",
            _seller_crm_context(
                request,
                title="Сайт не налаштовано — CRM продавця",
                current_page="website",
                account=account,
                subscription=subscription,
                site=None,
                site_missing=True,
                has_website=False,
                has_cars=False,
                has_services=False,
                config={},
                services=[],
                cars=[],
                brands=[],
                models=[],
                media=[],
                live_url="#",
                section=section,
                status=status,
                themes=get_theme_presets(),
                module_keys=MODULE_KEYS,
            ),
        )

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
            title="Керування сайтом — CRM продавця",
            current_page="website",
            account=account,
            subscription=subscription,
            site=site,
            has_website=True,
            has_cars=bool(cars),
            has_services=bool(services),
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
        return HTMLResponse(
            "<h1>Сайт ще не налаштовано</h1><p>Поверніться до CRM продавця та налаштуйте сайт.</p>",
            status_code=200,
        )
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
