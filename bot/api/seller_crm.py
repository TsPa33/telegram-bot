import json
import logging
import os
import re
import secrets
import tempfile
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from pathlib import Path
from html import escape
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.repositories.car_repo import (
    archive_seller_car,
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
from bot.database.repositories.product_repo import get_seller_products
from bot.database.repositories.part_repo import (
    PART_CATEGORY_OPTIONS,
    VALID_PART_STATUSES,
    bulk_update_parts_status_by_category,
    create_manual_part,
    generate_parts_for_car,
    get_car_part_categories,
    hide_parts_by_car,
    get_available_parts_for_site,
    get_part_by_id,
    get_parts_by_car_id,
    get_parts_by_car_id_filtered,
    get_parts_counters_by_car_ids,
    seller_owns_car,
    normalize_part_category,
    update_part_fields,
    update_generated_parts_status,
    update_part_photo,
    update_part_price,
    update_part_status,
)
from bot.database.repositories.seller_crm_repo import (
    SellerCrmGarageFullError,
    create_crm_session,
    create_seller_crm_car,
    delete_crm_session,
    get_crm_account_by_slug,
    get_crm_account_for_login,
    get_crm_session,
    set_crm_password_hash_if_empty,
    set_crm_password_hash_for_verified_reset,
    get_seller_crm_dashboard,
    get_seller_crm_analytics,
    get_seller_crm_car_detail,
    get_seller_crm_content_summary,
    get_seller_crm_lead_detail,
    get_seller_crm_offer_detail,
    get_seller_crm_public_profile,
    update_seller_crm_profile,
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
    update_seller_crm_car_photo,
)
from bot.database.repositories.lead_thread_repo import (
    LEAD_THREAD_READ_READ,
    LEAD_THREAD_SENDER_SELLER,
    attach_telegram_delivery_to_thread_message,
    create_lead_thread_message,
    get_buyer_thread_delivery_context,
    list_lead_thread_messages,
    mark_lead_thread_messages_read,
)
from bot.database.repositories.product_repo import (
    create_product,
    get_product_by_id,
    get_seller_product_donor_cars,
    get_seller_products,
    set_product_status,
    update_product,
    update_product_photo,
)
from bot.database.migrations_runner import get_seller_lead_action_constraints
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
from bot.domain.statuses import (
    CAR_STATUS_INACTIVE_VALUES,
    CRM_LEAD_STATUS_DECLINED,
    CRM_LEAD_STATUS_IN_WORK,
    CRM_LEAD_STATUS_NEW,
    CRM_LEAD_STATUS_REPLIED,
    CRM_LEAD_STATUS_SELECTED,
    CRM_LEAD_STATUS_SKIPPED,
    CRM_LEAD_STATUS_ARCHIVED,
    CRM_LEAD_STATUSES,
    CRM_OFFER_STATUS_ACTIVE,
    CRM_OFFER_STATUS_ALL,
    CRM_OFFER_STATUS_REJECTED,
    CRM_OFFER_STATUS_SELECTED,
    CRM_OFFER_STATUSES,
    BUYER_OFFER_STATUS_ACCEPTED,
    BUYER_OFFER_STATUS_PENDING,
    BUYER_OFFER_STATUS_REJECTED,
    NOTIFICATION_STATUS_CANCELLED,
    NOTIFICATION_STATUS_FAILED,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_STATUS_SENT,
    SELLER_LEAD_ACTION_DECLINED,
    SELLER_LEAD_ACTION_ARCHIVED,
    SELLER_LEAD_ACTION_OFFERED,
    SELLER_LEAD_ACTION_SKIPPED,
    SELLER_LEAD_ACTION_VIEWED,
    get_car_display_status,
    get_crm_lead_status_meta,
    get_crm_offer_status_meta,
    get_service_display_status,
    is_car_active_status,
    normalize_text_status,
)
from bot.services.domain_service import build_site_url
from bot.services.import_service import (
    PRODUCT_IMPORT_COLUMNS,
    generate_product_import_csv_template,
    generate_product_import_xlsx_template,
    import_products_from_file,
)
from bot.services.seller_crm import (
    SELLER_CRM_SESSION_DAYS,
    hash_crm_password,
    verify_crm_password_reset_token,
    validate_crm_password,
    validate_crm_slug,
    verify_crm_password,
)
from bot.services.seller_offer_service import submit_seller_offer_from_crm
from bot.services.telegram_sender import send_message_to_buyer
from bot.services.buyer_chat_presence import is_buyer_in_chat
from bot.services.site_config import get_theme_presets, merge_with_default
from bot.services.storage import upload_image
from bot.services.liqpay_service import LiqPayService
from bot.config import LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY, LIQPAY_CALLBACK_URL

router = APIRouter(prefix="/crm/seller")
templates = Jinja2Templates(directory="bot/api/templates")
SELLER_CRM_COOKIE = "seller_crm_session"
DEMO_CRM_SLUG = "demo"
DEMO_SELLER_ID = 0
logger = logging.getLogger(__name__)
liqpay = LiqPayService(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)


LEAD_STATUS_TABS = [
    {"key": CRM_LEAD_STATUS_NEW, "label": "Нова заявка", "empty": "Нових заявок поки немає."},
    {"key": CRM_LEAD_STATUS_IN_WORK, "label": "Покупець очікує відповідь", "empty": "Немає заявок, які очікують відповіді."},
    {"key": CRM_LEAD_STATUS_REPLIED, "label": "Відповідь надіслана", "empty": "Немає заявок із надісланою пропозицією."},
    {"key": CRM_LEAD_STATUS_SELECTED, "label": "Покупець підтвердив", "empty": "Покупці ще не обрали ваші пропозиції."},
    {"key": CRM_LEAD_STATUS_DECLINED, "label": "Покупець відхилив", "empty": "Відхилених заявок немає."},
    {"key": CRM_LEAD_STATUS_SKIPPED, "label": "Заявку закрито", "empty": "Закритих заявок немає."},
    {"key": CRM_LEAD_STATUS_ARCHIVED, "label": "Архів", "empty": "Архів заявок порожній."},
]
ALLOWED_LEAD_STATUSES = CRM_LEAD_STATUSES

OFFER_STATUS_TABS = [
    {"key": CRM_OFFER_STATUS_ACTIVE, "label": "Очікують вибору", "empty": "Немає пропозицій, які очікують вибору покупця."},
    {"key": CRM_OFFER_STATUS_SELECTED, "label": "Обрані покупцем", "empty": "Покупці ще не обрали ваші пропозиції."},
    {"key": CRM_OFFER_STATUS_REJECTED, "label": "Не обрані", "empty": "Немає відхилених пропозицій."},
    {"key": CRM_OFFER_STATUS_ALL, "label": "Усі пропозиції", "empty": "Надісланих пропозицій ще немає."},
]
ALLOWED_OFFER_STATUSES = CRM_OFFER_STATUSES

ALLOWED_CAR_PHOTO_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
CAR_PHOTO_MAX_BYTES = 5 * 1024 * 1024
CAR_PHOTO_SUFFIX_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
UA_PHONE_RE = re.compile(r"^\+380\d{9}$")


MODULE_KEYS = [
    ("hero", "Перший екран"),
    ("services", "Послуги"),
    ("cars", "Авто"),
    ("products", "Товари / запчастини"),
    ("gallery", "Галерея"),
    ("works", "Наші роботи"),
    ("pricing", "Ціни"),
    ("contacts", "Контакти"),
    ("map", "Карта"),
    ("cta", "Заклик до дії"),
    ("reviews", "Відгуки"),
    ("footer", "Футер"),
]

WEBSITE_EDITABLE_BLOCKS: dict[str, dict[str, str]] = {
    "hero": {"name": "Перший екран", "description": "Головний банер і ключове повідомлення."},
    "about": {"name": "Про компанію", "description": "Коротко про вашу компанію та досвід."},
    "cars": {"name": "Авто на розборі", "description": "Блок із авто, які ви зараз демонтуєте."},
    "products": {"name": "Товари / запчастини", "description": "Показ каталогу товарів і запчастин."},
    "services": {"name": "Послуги", "description": "Перелік послуг на вашому сайті."},
    "contacts": {"name": "Контакти", "description": "Телефони, месенджери та адреса."},
    "map": {"name": "Карта", "description": "Відображення локації на карті."},
    "footer": {"name": "Футер", "description": "Нижній блок із службовою інформацією."},
}


def _is_demo_crm_slug(crm_slug: str | None) -> bool:
    return (crm_slug or "").strip().lower() == DEMO_CRM_SLUG


def _is_demo_account(account: dict[str, Any] | None) -> bool:
    return bool(account and _is_demo_crm_slug(str(account.get("crm_slug") or "")))


def _demo_crm_account() -> dict[str, Any]:
    return {
        "seller_id": DEMO_SELLER_ID,
        "crm_slug": DEMO_CRM_SLUG,
        "shop_name": "Demo Auto Hub",
        "name": "Demo Auto Hub",
        "username": "CarPotbot",
        "phone": "+380 67 000 00 00",
        "city": "Київ",
        "website": "https://demo.carpot.com.ua",
        "has_site": True,
        "crm_enabled": True,
        "is_active": True,
    }


def _demo_subscription() -> dict[str, Any]:
    return {"expires_at": datetime.utcnow() + timedelta(days=30), "demo": True}


def _demo_content_summary() -> dict[str, Any]:
    return {
        "active_cars": 2,
        "active_services": 3,
        "products_total": 12,
        "cars_without_photo": 0,
        "cars_without_description": 0,
        "garage_slots_total": 10,
        "garage_slots_used": 2,
        "garage_slots_free": 8,
    }


def _demo_settings_summary() -> dict[str, Any]:
    return {
        "crm_slug": DEMO_CRM_SLUG,
        "crm_account_status": "active",
        "crm_enabled": True,
        "account_created_at": datetime.utcnow() - timedelta(days=45),
        "seller": {
            "shop_name": "Demo Auto Hub",
            "name": "Demo Auto Hub",
            "city": "Київ",
            "website": "https://demo.carpot.com.ua",
            "phone": "+380 67 000 00 00",
            "username": "CarPotbot",
        },
        "active_paid_seller_subscriptions": [],
        "garage_slots_available": True,
        "active_garage_slots": 10,
        "used_garage_slots": 2,
        "free_garage_slots": 8,
        "active_cars_count": 2,
        "latest_payments": [],
        "site": {"subdomain": "demo"},
        "has_site": True,
    }


def _demo_public_profile() -> dict[str, Any]:
    return {
        "shop_name": "Demo Auto Hub",
        "name": "Demo Auto Hub",
        "phone": "+380 67 000 00 00",
        "city": "Київ",
        "description": "Демо-профіль CarPot для перевірки робочого простору продавця.",
        "photo_id": "",
        "is_verified": True,
        "active_cars_count": 2,
        "active_services_count": 3,
        "has_site": True,
        "website": "https://demo.carpot.com.ua",
        "response_activity": {"avg_response_seconds": 18 * 60},
    }


def _demo_analytics() -> dict[str, Any]:
    return {
        "visits_today": 186,
        "leads_today": 14,
        "telegram_clicks_today": 42,
        "active_listings": 38,
        "conversion": 7.5,
        "routed_requests": 18,
        "viewed_requests": 15,
        "offers_sent": 9,
        "offers_selected": 3,
        "declined_requests": 2,
        "skipped_requests": 1,
        "offers_rejected": 4,
        "average_response_seconds": 18 * 60,
        "has_website": True,
    }


def _demo_site() -> dict[str, Any]:
    return {
        "seller_id": DEMO_SELLER_ID,
        "subdomain": DEMO_CRM_SLUG,
        "config_draft": {},
        "config_live": {},
    }

def _seller_crm_context(request: Request, **kwargs):
    context = {"request": request, "title": "Кабінет продавця"}
    context.update(kwargs)
    account = context.get("account")
    if _is_demo_account(account):
        context["demo_mode"] = True
    context.setdefault("demo_mode", False)
    if account and "crm_slug" not in context:
        context["crm_slug"] = account.get("crm_slug")
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
        SELLER_LEAD_ACTION_VIEWED: "Заявку позначено переглянутою.",
        SELLER_LEAD_ACTION_DECLINED: "Заявку відхилено для вашого робочого простору.",
        SELLER_LEAD_ACTION_SKIPPED: "Заявку пропущено для вашого робочого простору.",
        "reopened": "Заявку повернуто в роботу.",
        SELLER_LEAD_ACTION_ARCHIVED: "Заявку закрито й перенесено в архів.",
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




PRODUCT_STATUS_OPTIONS = [
    ("active", "Активний"),
    ("inactive", "Неактивний"),
]
PRODUCT_STOCK_STATUS_OPTIONS = [
    ("available", "В наявності"),
    ("low_stock", "Мало на складі"),
    ("sold", "Продано"),
    ("preorder", "Передзамовлення"),
]
PRODUCT_STATUS_LABELS = {
    "active": "Активний",
    "inactive": "Неактивний",
    "archived": "Архів",
}
PRODUCT_STOCK_LABELS = {
    "available": "В наявності",
    "low_stock": "Мало на складі",
    "sold": "Продано",
    "preorder": "Передзамовлення",
}
PRODUCT_STATUS_CLASSES = {
    "active": "status-success",
    "inactive": "status-rejected",
    "archived": "status-waiting",
    "sold": "status-viewed",
}
PRODUCT_STOCK_CLASSES = {
    "available": "status-success",
    "low_stock": "status-waiting",
    "sold": "status-viewed",
    "preorder": "status-waiting",
}

PART_CATEGORY_LABELS = dict(PART_CATEGORY_OPTIONS)
ALLOWED_PART_CATEGORIES = set(PART_CATEGORY_LABELS)
PART_STATUS_LABELS = {
    "draft": "Чернетка",
    "available": "В наявності",
    "sold": "Продано",
    "hidden": "Приховано",
}
PART_STATUS_CLASSES = {
    "draft": "status-waiting",
    "available": "status-success",
    "sold": "status-viewed",
    "hidden": "status-rejected",
}


def _normalize_part_name(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _normalize_part_search(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _parse_part_price(value: str | None) -> tuple[Decimal | None, str | None]:
    raw = (value or "").strip().lower().replace("грн", "").replace(" ", "").replace(",", ".")
    if not raw:
        return None, None
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None, "Ціна має бути числом."
    if amount < 0:
        return None, "Ціна не може бути від’ємною."
    if amount > Decimal("100000000"):
        return None, "Ціна занадто велика."
    return amount, None


def _part_form_payload(**values) -> dict[str, Any]:
    defaults = {
        "name": "",
        "category": "body",
        "status": "available",
        "price": "",
        "description": "",
    }
    defaults.update(values)
    for key, value in list(defaults.items()):
        if value is None:
            defaults[key] = ""
        elif isinstance(value, str):
            defaults[key] = value.strip()
    return defaults


def _validate_part_form(name: str, category: str, status: str, price: str, description: str) -> tuple[str, Decimal | None, str | None]:
    normalized_name = _normalize_part_name(name)
    if not normalized_name:
        return "", None, "Назва запчастини обов’язкова."
    if len(normalized_name) > 200:
        return "", None, "Назва має бути до 200 символів."
    normalized_category = normalize_part_category(category)
    if normalized_category not in ALLOWED_PART_CATEGORIES:
        return "", None, "Оберіть коректну категорію."
    if status not in VALID_PART_STATUSES:
        return "", None, "Оберіть коректний статус."
    if len((description or "").strip()) > 1000:
        return "", None, "Опис має бути до 1000 символів."
    parsed_price, price_error = _parse_part_price(price)
    if price_error:
        return "", None, price_error
    return normalized_name, parsed_price, None


def _prepare_part(item: Any) -> dict[str, Any]:
    part = dict(item or {})
    status = part.get("status") or "draft"
    category = normalize_part_category(part.get("category"))
    part["category"] = category
    description = (part.get("description") or "").strip()
    part["status_label"] = PART_STATUS_LABELS.get(status, status)
    part["status_class"] = PART_STATUS_CLASSES.get(status, "status-waiting")
    part["category_label"] = PART_CATEGORY_LABELS.get(category, category)
    part["description_preview"] = description[:180] + ("…" if len(description) > 180 else "") if description else ""
    part["price_display"] = f"₴ {_format_price(part.get('price'))}" if part.get("price") is not None else "Ціна не вказана"
    return part


def _parse_product_money(value: str | None) -> tuple[str | None, str | None]:
    raw = (value or "").strip().replace(" ", "").replace(",", ".")
    if not raw:
        return None, None
    try:
        amount = float(raw)
    except ValueError:
        return None, "Ціна має бути числом."
    if amount < 0:
        return None, "Ціна не може бути від’ємною."
    if amount > 100_000_000:
        return None, "Ціна занадто велика."
    return f"{amount:.2f}", None


def _parse_product_quantity(value: str | None) -> tuple[int, str | None]:
    raw = (value or "").strip()
    if not raw:
        return 1, None
    if not raw.isdigit():
        return 1, "Кількість має бути цілим числом."
    quantity = int(raw)
    if quantity < 0:
        return 1, "Кількість не може бути від’ємною."
    if quantity > 1_000_000:
        return 1, "Кількість занадто велика."
    return quantity, None


def _product_form_payload(**values) -> dict[str, Any]:
    defaults = {
        "title": "",
        "category": "",
        "brand": "",
        "model": "",
        "oem_code": "",
        "condition": "",
        "description": "",
        "price": "",
        "quantity": "1",
        "stock_status": "available",
        "status": "active",
        "donor_car_id": "",
    }
    defaults.update(values)
    for key, value in list(defaults.items()):
        if value is None:
            defaults[key] = ""
        elif isinstance(value, str):
            defaults[key] = value.strip()
    return defaults


def _validate_product_form(title: str, category: str, description: str, price: str, quantity: str, stock_status: str, status: str) -> tuple[str | None, int, str | None]:
    if not (title or "").strip():
        return None, 1, "Назва товару обов’язкова."
    if not (category or "").strip():
        return None, 1, "Категорія обов’язкова."
    if len((title or "").strip()) > 180:
        return None, 1, "Назва має бути до 180 символів."
    if len((category or "").strip()) > 120:
        return None, 1, "Категорія має бути до 120 символів."
    if len((description or "").strip()) > 3000:
        return None, 1, "Опис має бути до 3000 символів."
    if stock_status not in dict(PRODUCT_STOCK_STATUS_OPTIONS):
        return None, 1, "Оберіть коректний складський статус."
    if status not in dict(PRODUCT_STATUS_OPTIONS):
        return None, 1, "Оберіть коректний статус товару."
    parsed_price, price_error = _parse_product_money(price)
    if price_error:
        return None, 1, price_error
    parsed_quantity, quantity_error = _parse_product_quantity(quantity)
    if quantity_error:
        return None, 1, quantity_error
    return parsed_price, parsed_quantity, None


def _prepare_product(product: Any) -> dict[str, Any]:
    item = dict(product or {})
    status = item.get("status") or "inactive"
    stock_status = item.get("stock_status") or "available"
    display_status = "sold" if stock_status == "sold" else status
    item["display_status"] = display_status
    item["status_label"] = PRODUCT_STOCK_LABELS.get("sold") if display_status == "sold" else PRODUCT_STATUS_LABELS.get(status, status)
    item["status_class"] = PRODUCT_STATUS_CLASSES.get(display_status, "status-waiting")
    item["stock_label"] = PRODUCT_STOCK_LABELS.get(stock_status, stock_status)
    item["stock_class"] = PRODUCT_STOCK_CLASSES.get(stock_status, "status-waiting")
    item["is_active"] = status == "active"
    item["has_photo"] = bool(item.get("photo_url"))
    item["photo_is_url"] = isinstance(item.get("photo_url"), str) and item["photo_url"].startswith(("http://", "https://"))
    item["has_description"] = bool((item.get("description") or "").strip())
    item["has_price"] = item.get("price") is not None
    item["has_oem"] = bool((item.get("oem_code") or "").strip())
    item["content_completeness"] = round(
        100
        * sum([True, bool(item.get("category")), item["has_description"], item["has_price"], item["has_photo"], item["has_oem"]])
        / 6
    )
    return item


def _product_form_from_record(product: Any) -> dict[str, Any]:
    item = dict(product or {})
    return _product_form_payload(
        title=item.get("title"),
        category=item.get("category"),
        brand=item.get("brand"),
        model=item.get("model"),
        oem_code=item.get("oem_code"),
        condition=item.get("condition"),
        description=item.get("description"),
        price="" if item.get("price") is None else str(item.get("price")),
        quantity=str(item.get("quantity") if item.get("quantity") is not None else 1),
        stock_status=item.get("stock_status") or "available",
        status=item.get("status") or "active",
        donor_car_id="" if item.get("donor_car_id") is None else str(item.get("donor_car_id")),
    )


def _car_form_payload(description: str = "", status: str = "active", is_catalog: bool = False) -> dict[str, Any]:
    normalized_status = normalize_text_status(status, CRM_OFFER_STATUS_ACTIVE)
    if is_car_active_status(normalized_status):
        normalized_status = CRM_OFFER_STATUS_ACTIVE
    elif normalized_status in CAR_STATUS_INACTIVE_VALUES:
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
            title="Додати авто — кабінет продавця CarPot",
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


def _login_redirect(crm_slug: str):
    raise HTTPException(
        status_code=303,
        detail=f"/crm/seller/login?slug={crm_slug}",
    )


def _setup_password_redirect(crm_slug: str):
    raise HTTPException(
        status_code=303,
        detail=f"/crm/seller/setup-password?slug={crm_slug}",
    )


async def _current_session(request: Request):
    token = request.cookies.get(SELLER_CRM_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Потрібен вхід у кабінет продавця")

    session = await get_crm_session(token)
    if not session or _is_expired(session["expires_at"]):
        raise HTTPException(status_code=401, detail="Сесія кабінету продавця завершилась")
    if not session["is_active"] or not session["crm_enabled"]:
        raise HTTPException(status_code=403, detail="Кабінет продавця вимкнено")

    return session, None


async def _authorized_account(request: Request, crm_slug: str):
    if _is_demo_crm_slug(crm_slug):
        return _demo_crm_account(), _demo_subscription()

    account = await get_crm_account_by_slug(crm_slug)
    if not account:
        raise HTTPException(status_code=404, detail="Акаунт кабінету не знайдено")
    if not account.get("password_hash"):
        _setup_password_redirect(account["crm_slug"])

    try:
        session, subscription = await _current_session(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            _login_redirect(crm_slug)
        raise

    if session["seller_id"] != account["seller_id"] or session["crm_slug"] != crm_slug:
        token = request.cookies.get(SELLER_CRM_COOKIE)
        if token:
            await delete_crm_session(token)
        _login_redirect(crm_slug)

    return account, subscription


def _redirect(crm_slug: str, section: str = "website", status: str = "saved"):
    return RedirectResponse(
        url=f"/crm/seller/{crm_slug}/website?status={status}#{section}",
        status_code=303,
    )


def _as_config(site) -> dict[str, Any]:
    raw = site.get("config_draft") if site else {}
    return merge_with_default(raw if isinstance(raw, dict) else {})


def _as_live_config(site) -> dict[str, Any]:
    raw = site.get("config_live") if site else {}
    return merge_with_default(raw if isinstance(raw, dict) else {})




async def get_current_seller_site_or_404(seller_id: int) -> dict[str, Any]:
    site = await get_site_by_seller(seller_id)
    if not site:
        raise HTTPException(status_code=404, detail="Сайт продавця не знайдено")
    return site


async def update_current_site_draft(seller_id: int, patch: dict[str, Any]) -> bool:
    safe_patch = patch if isinstance(patch, dict) else {}
    return await update_site_config_draft(seller_id, safe_patch)


async def publish_current_site(seller_id: int) -> bool:
    return await publish_site(seller_id)

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
    return title or row.get("category") or row.get("request_type") or "Заявка"


def _request_status_label(row) -> str:
    offer_status = row.get("offer_status")
    action = row.get("seller_action")
    if offer_status == BUYER_OFFER_STATUS_ACCEPTED:
        return "Обрано покупцем"
    if offer_status == BUYER_OFFER_STATUS_PENDING:
        return "Відповідь надіслана"
    if offer_status == BUYER_OFFER_STATUS_REJECTED:
        return "Не обрано"
    if action == SELLER_LEAD_ACTION_DECLINED:
        return "Відхилено"
    if action == SELLER_LEAD_ACTION_SKIPPED:
        return "Пропущено"
    if action == SELLER_LEAD_ACTION_VIEWED:
        return "Покупець очікує"
    return "Нова · треба відповісти"


def _request_operational_state(row) -> dict[str, str | bool]:
    offer_status = row.get("offer_status")
    action = row.get("seller_action")
    if offer_status == BUYER_OFFER_STATUS_ACCEPTED:
        return {
            "class": "status-success",
            "action": "Продовжити діалог",
            "tone": "buyer-selected",
            "needs_attention": True,
        }
    if offer_status == BUYER_OFFER_STATUS_PENDING:
        return {
            "class": "status-replied",
            "action": "Відкрити діалог",
            "tone": "active-dialog",
            "needs_attention": False,
        }
    if action == SELLER_LEAD_ACTION_VIEWED:
        return {
            "class": "status-waiting",
            "action": "Відповісти",
            "tone": "buyer-waiting",
            "needs_attention": True,
        }
    if action in {SELLER_LEAD_ACTION_DECLINED, SELLER_LEAD_ACTION_SKIPPED} or offer_status == BUYER_OFFER_STATUS_REJECTED:
        return {
            "class": "status-viewed",
            "action": "Переглянути",
            "tone": "secondary",
            "needs_attention": False,
        }
    return {"class": "status-new", "action": "Відповісти", "tone": "new-lead", "needs_attention": True}


def _activity_label(row) -> str:
    action = row.get("action")
    labels = {
        "buyer_request_created": "Нова заявка · покупець очікує",
        "buyer_offer_created": "Відповідь надіслано покупцю",
        "buyer_offer_accepted": "Покупець обрав вашу пропозицію",
        SELLER_LEAD_ACTION_OFFERED: "Пропозицію надіслано",
    }
    return labels.get(action, "Важливе оновлення заявки")


def _prepare_marketplace_requests(rows) -> list[dict[str, Any]]:
    prepared = []
    for row in rows or []:
        item = dict(row)
        if (
            item.get("seller_status") == CRM_LEAD_STATUS_ARCHIVED
            or item.get("offer_status") == BUYER_OFFER_STATUS_REJECTED
            or (item.get("marketplace_status") or "").lower() == "closed"
            or item.get("selected_other_seller")
        ):
            continue
        item["title"] = _request_title(item)
        item["short_description"] = item.get("description") or item.get("message") or "Покупець не додав опис"
        item["status_label"] = _request_status_label(item)
        operational_state = _request_operational_state(item)
        item["status_class"] = operational_state["class"]
        item["primary_action_label"] = operational_state["action"]
        item["operational_tone"] = operational_state["tone"]
        item["needs_attention"] = operational_state["needs_attention"]
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


def _lead_status_meta(status: str | None) -> dict[str, Any]:
    meta = get_crm_lead_status_meta(status or CRM_LEAD_STATUS_NEW)
    return {**meta, "class": meta["css_class"]}


def _offer_status_meta(status: str | None) -> dict[str, Any]:
    meta = get_crm_offer_status_meta(status or CRM_OFFER_STATUS_ACTIVE)
    return {**meta, "class": meta["css_class"]}


def _prepare_marketplace_leads(rows, *, active_status: str = CRM_LEAD_STATUS_NEW) -> list[dict[str, Any]]:
    prepared = []
    archive_view = active_status == CRM_LEAD_STATUS_ARCHIVED
    for row in rows or []:
        item = dict(row)
        if not archive_view and (
            item.get("seller_status") == CRM_LEAD_STATUS_ARCHIVED
            or item.get("offer_status") == BUYER_OFFER_STATUS_REJECTED
            or (item.get("marketplace_status") or "").lower() == "closed"
            or item.get("selected_other_seller")
        ):
            continue
        item["title"] = item.get("title") or _request_title(item)
        item["short_description"] = item.get("description") or "Покупець не додав опис"
        status_meta = _lead_status_meta(item.get("seller_status"))
        item["status_label"] = status_meta["label"]
        item["status_class"] = status_meta["class"]
        item["match_reasons_label"] = None
        status = item.get("seller_status")
        item["can_mark_viewed"] = status == "new" and not item.get("has_viewed")
        item["can_decline"] = status not in {CRM_LEAD_STATUS_DECLINED, CRM_LEAD_STATUS_SKIPPED, CRM_LEAD_STATUS_SELECTED}
        item["can_skip"] = status not in {CRM_LEAD_STATUS_DECLINED, CRM_LEAD_STATUS_SKIPPED, CRM_LEAD_STATUS_SELECTED}
        if status in {CRM_LEAD_STATUS_NEW, CRM_LEAD_STATUS_IN_WORK}:
            item["next_action_label"] = "Відповісти покупцю"
            item["attention_label"] = "Потребує дії"
            item["attention_class"] = "status-new" if status == CRM_LEAD_STATUS_NEW else "status-waiting"
        elif status == CRM_LEAD_STATUS_REPLIED:
            item["next_action_label"] = "Продовжити діалог"
            item["attention_label"] = "Активний діалог"
            item["attention_class"] = "status-replied"
        elif status == CRM_LEAD_STATUS_SELECTED:
            item["next_action_label"] = "Відкрити контакт"
            item["attention_label"] = "Покупець обрав вас"
            item["attention_class"] = "status-success"
        else:
            item["next_action_label"] = "Переглянути"
            item["attention_label"] = "Без термінової дії"
            item["attention_class"] = "status-viewed"
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
    thread_messages = [dict(message) for message in prepared.get("thread_messages", [])]
    prepared["thread_messages"] = thread_messages
    prepared["has_thread"] = bool(thread_messages or offer or marketplace.get("is_selected"))

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
        offer["price_display"] = "Договірна" if offer.get("price") is None else f"₴ {offer['price_label']}"
        offer["price_input"] = "" if offer.get("price") is None else str(offer.get("price"))

    selected_this_seller = bool(marketplace.get("is_selected"))
    selected_other_seller = bool(marketplace.get("selected_other_seller"))
    request_closed = (marketplace.get("status") or "").lower() == "closed"

    if selected_this_seller:
        marketplace["state_label"] = "Покупець обрав вашу пропозицію"
        marketplace["state_class"] = "status-success"
    elif selected_other_seller:
        marketplace["state_label"] = "Покупець обрав іншого продавця"
        marketplace["state_class"] = "status-rejected"
    elif request_closed:
        marketplace["state_label"] = "Заявку закрито"
        marketplace["state_class"] = "status-rejected"
    else:
        marketplace["state_label"] = "Очікує рішення покупця"
        marketplace["state_class"] = "status-waiting"

    seller_status = seller_state.get("seller_status")
    request_closed = request_data.get("marketplace_status") == "closed" or marketplace.get("status") == "closed"
    selected_other_seller = bool(marketplace.get("selected_other_seller"))
    selected_this_seller = bool(marketplace.get("is_selected")) and not selected_other_seller
    blocked_by_seller_action = seller_status in {CRM_LEAD_STATUS_DECLINED, CRM_LEAD_STATUS_SKIPPED} and not offer

    prepared["can_mark_viewed"] = not seller_state.get("has_viewed")
    prepared["can_decline"] = seller_status not in {CRM_LEAD_STATUS_DECLINED, CRM_LEAD_STATUS_SKIPPED, CRM_LEAD_STATUS_SELECTED} and not selected_other_seller and not selected_this_seller
    prepared["can_skip"] = seller_status not in {CRM_LEAD_STATUS_DECLINED, CRM_LEAD_STATUS_SKIPPED, CRM_LEAD_STATUS_SELECTED} and not selected_other_seller and not selected_this_seller
    prepared["can_reopen"] = seller_status in {CRM_LEAD_STATUS_DECLINED, CRM_LEAD_STATUS_SKIPPED} and not selected_other_seller and not selected_this_seller and not request_closed
    prepared["selected_this_seller"] = selected_this_seller
    prepared["selected_other_seller"] = selected_other_seller
    prepared["has_existing_offer"] = bool(offer)
    prepared["may_respond"] = not selected_other_seller and not selected_this_seller and not request_closed and not blocked_by_seller_action
    prepared["can_archive"] = seller_status != "archived"
    if selected_this_seller:
        prepared["response_block_reason"] = "Покупець обрав вашу пропозицію."
    elif selected_other_seller:
        prepared["response_block_reason"] = "Покупець уже обрав іншого продавця."
    elif request_closed:
        prepared["response_block_reason"] = "Заявку закрито, відповідь більше недоступна."
    elif blocked_by_seller_action:
        prepared["response_block_reason"] = "Цю заявку вже відхилено або пропущено."
    else:
        prepared["response_block_reason"] = None

    if selected_this_seller:
        prepared["operational_status"] = {
            "label": "Покупець обрав вашу пропозицію",
            "description": "Контакти покупця відкриті в блоці праворуч. Далі працюйте з комунікацією та виконанням запиту.",
            "class": "status-success",
        }
    elif selected_other_seller:
        prepared["operational_status"] = {
            "label": "Покупець обрав іншого продавця",
            "description": "Форма відповіді закрита, але заявка лишається доступною для перегляду контексту.",
            "class": "status-rejected",
        }
    elif offer:
        prepared["operational_status"] = {
            "label": "Відповідь надіслана покупцю",
            "description": "Очікуйте рішення покупця або оновіть відповідь, якщо умови змінилися.",
            "class": "status-replied",
        }
    elif prepared["may_respond"]:
        prepared["operational_status"] = {
            "label": "Покупець очікує відповідь",
            "description": "Перевірте потребу покупця й надішліть ціну та короткий коментар.",
            "class": seller_state.get("status_class") or "status-new",
        }
    else:
        prepared["operational_status"] = {
            "label": prepared["response_block_reason"] or seller_state.get("status_label") or "Стан заявки",
            "description": "Деталі заявки доступні нижче без зміни бізнес-станів.",
            "class": seller_state.get("status_class") or "status-viewed",
        }

    low_value_timeline_sources = {"notification"}
    prepared["request"] = request_data
    prepared["seller_state"] = seller_state
    prepared["offer"] = offer
    prepared["marketplace"] = marketplace
    prepared["timeline"] = [
        event for event in (prepared.get("timeline") or [])
        if event.get("source") not in low_value_timeline_sources
    ]
    return prepared


def _offer_workspace_status_meta(offer: dict[str, Any]) -> dict[str, Any]:
    raw_status = offer.get("offer_status") or offer.get("status")
    if offer.get("is_selected"):
        raw_status = CRM_OFFER_STATUS_SELECTED
    elif raw_status == BUYER_OFFER_STATUS_ACCEPTED:
        raw_status = CRM_OFFER_STATUS_SELECTED
    elif raw_status == BUYER_OFFER_STATUS_REJECTED:
        raw_status = CRM_OFFER_STATUS_REJECTED
    else:
        raw_status = CRM_OFFER_STATUS_ACTIVE

    meta = get_crm_offer_status_meta(raw_status)
    state = "selected" if raw_status == CRM_OFFER_STATUS_SELECTED else "rejected" if raw_status == CRM_OFFER_STATUS_REJECTED else "waiting"
    return {**meta, "class": meta["css_class"], "state": state}


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
    prepared["thread_messages"] = [dict(message) for message in prepared.get("thread_messages", [])]
    selection = {**prepared.get("selection", {})}

    request_data["title"] = request_data.get("title") or _request_title(request_data)
    request_data["description"] = request_data.get("description") or "Покупець не додав детальний опис."
    offer["price_label"] = _format_price(offer.get("price"))
    offer["price_display"] = "Договірна" if offer.get("price") is None else f"₴ {offer['price_label']}"

    status_meta = _offer_workspace_status_meta({
        "status": offer.get("status"),
        "is_selected": selection.get("is_selected"),
    })
    offer["status_label"] = status_meta["label"]
    offer["status_class"] = status_meta["class"]
    selection["state"] = status_meta["state"]
    selection["state_label"] = status_meta["label"]
    selection["state_class"] = status_meta["class"]
    if status_meta["state"] == "selected":
        selection["operational_label"] = "Пропозицію обрано покупцем"
        selection["operational_hint"] = "Покупець підтвердив саме цю відповідь. Перейдіть до заявки, щоб працювати з контактом покупця."
    elif status_meta["state"] == "rejected":
        selection["operational_label"] = "Покупець обрав іншого продавця"
        selection["operational_hint"] = "Ця пропозиція закрита для подальшого вибору, але контекст заявки доступний за посиланням."
    else:
        selection["operational_label"] = "Очікує рішення покупця"
        selection["operational_hint"] = "Пропозицію надіслано. Якщо потрібно змінити відповідь — відкрийте пов’язану заявку."

    prepared["offer"] = offer
    prepared["request"] = request_data
    prepared["selection"] = selection
    prepared["timeline"] = [
        event for event in (prepared.get("timeline") or [])
        if event.get("source") != "notification"
    ]
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


async def _upload_validated_car_photo(file: UploadFile | None) -> tuple[str | None, str | None]:
    if not file or not file.filename:
        return None, "empty_photo"

    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CAR_PHOTO_MIME_TYPES:
        return None, "invalid_photo_type"

    suffix = CAR_PHOTO_SUFFIX_BY_MIME.get(content_type, Path(file.filename).suffix or ".jpg")
    fd, temp_path = tempfile.mkstemp(prefix="carpot-crm-car-", suffix=suffix)
    total_size = 0
    try:
        with os.fdopen(fd, "wb") as temp_file:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > CAR_PHOTO_MAX_BYTES:
                    return None, "photo_too_large"
                temp_file.write(chunk)

        if total_size <= 0:
            return None, "empty_photo"

        image_url = await upload_image(temp_path)
        if not image_url:
            return None, "photo_upload_failed"
        return image_url, None
    except Exception:
        logger.exception("CRM_CAR_PHOTO_UPLOAD_FAILED")
        return None, "photo_upload_failed"
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
            title="Демо кабінет CarPot",
            demo_mode=True,
            current_page="dashboard",
            account=_demo_crm_account(),
            subscription=_demo_subscription(),
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


def _seller_crm_login_value(account: dict[str, Any] | None) -> str:
    if not account:
        return ""
    if account.get("telegram_id") is not None:
        return str(account["telegram_id"])
    return str(account.get("username") or account.get("crm_slug") or "")


def _render_setup_password(
    request: Request,
    *,
    account: dict[str, Any] | None = None,
    slug: str = "",
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "seller_crm/setup_password.html",
        _seller_crm_context(
            request,
            title="Створення пароля кабінету",
            account=account,
            slug=slug,
            login=_seller_crm_login_value(account),
            error=error,
        ),
        status_code=status_code,
    )


def _render_reset_password(
    request: Request,
    *,
    account: dict[str, Any] | None = None,
    slug: str = "",
    identifier: str = "",
    token: str = "",
    error: str | None = None,
    message: str | None = None,
    token_verified: bool = False,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "seller_crm/reset_password.html",
        _seller_crm_context(
            request,
            title="Відновлення пароля кабінету",
            account=account,
            slug=slug,
            identifier=identifier,
            login=_seller_crm_login_value(account),
            token=token,
            token_verified=token_verified,
            error=error,
            message=message,
        ),
        status_code=status_code,
    )


@router.get("/login")
async def seller_crm_login_page(request: Request, slug: str | None = None):
    if slug:
        valid, normalized_slug = validate_crm_slug(slug)
        if valid:
            account = await get_crm_account_by_slug(normalized_slug)
            if account and account["is_active"] and account["crm_enabled"] and not account.get("password_hash"):
                return RedirectResponse(url=f"/crm/seller/setup-password?slug={account['crm_slug']}", status_code=303)

    return templates.TemplateResponse(
        "seller_crm/login.html",
        _seller_crm_context(request, slug=slug),
    )


@router.get("/setup-password")
async def seller_crm_setup_password_page(request: Request, slug: str | None = None):
    valid, normalized_slug = validate_crm_slug(slug)
    if not valid:
        return _render_setup_password(
            request,
            slug=slug or "",
            error="Некоректна адреса кабінету.",
            status_code=404,
        )

    account = await get_crm_account_by_slug(normalized_slug)
    if not account or not account["is_active"] or not account["crm_enabled"]:
        raise HTTPException(status_code=404, detail="Акаунт кабінету не знайдено")

    if account.get("password_hash"):
        return RedirectResponse(url=f"/crm/seller/login?slug={account['crm_slug']}", status_code=303)

    return _render_setup_password(request, account=dict(account), slug=account["crm_slug"])


@router.post("/setup-password")
async def seller_crm_setup_password(
    request: Request,
    slug: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    valid, normalized_slug = validate_crm_slug(slug)
    if not valid:
        return _render_setup_password(
            request,
            slug=slug,
            error="Некоректна адреса кабінету.",
            status_code=400,
        )

    account = await get_crm_account_by_slug(normalized_slug)
    if not account or not account["is_active"] or not account["crm_enabled"]:
        raise HTTPException(status_code=404, detail="Акаунт кабінету не знайдено")

    account = dict(account)
    if account.get("password_hash"):
        return RedirectResponse(url=f"/crm/seller/login?slug={account['crm_slug']}", status_code=303)

    if password != password_confirm:
        return _render_setup_password(
            request,
            account=account,
            slug=account["crm_slug"],
            error="Паролі не співпадають.",
            status_code=400,
        )

    password_valid, password_error = validate_crm_password(password)
    if not password_valid:
        return _render_setup_password(
            request,
            account=account,
            slug=account["crm_slug"],
            error=password_error,
            status_code=400,
        )

    updated_account = await set_crm_password_hash_if_empty(account["id"], hash_crm_password(password))
    if not updated_account:
        return RedirectResponse(url=f"/crm/seller/login?slug={account['crm_slug']}", status_code=303)

    logger.info(
        "CRM_FIRST_PASSWORD_SET seller_id=%s account_id=%s slug=%s",
        updated_account["seller_id"],
        updated_account["id"],
        updated_account["crm_slug"],
    )
    return RedirectResponse(url=f"/crm/seller/login?slug={updated_account['crm_slug']}", status_code=303)


@router.get("/reset-password")
async def seller_crm_reset_password_page(
    request: Request,
    slug: str | None = None,
    token: str | None = None,
):
    account: dict[str, Any] | None = None
    token_verified = False
    error = None
    normalized_slug = ""

    if slug:
        valid, normalized_slug = validate_crm_slug(slug)
        if valid:
            db_account = await get_crm_account_by_slug(normalized_slug)
            if db_account and db_account["is_active"] and db_account["crm_enabled"]:
                account = dict(db_account)
                token_verified, error = verify_crm_password_reset_token(account, token) if token else (False, None)
        else:
            error = "Некоректна адреса кабінету."

    return _render_reset_password(
        request,
        account=account,
        slug=normalized_slug or slug or "",
        identifier=_seller_crm_login_value(account),
        token=token or "",
        token_verified=token_verified,
        error=error,
        status_code=400 if error and token else 200,
    )


@router.post("/reset-password")
async def seller_crm_reset_password(
    request: Request,
    identifier: str = Form(""),
    slug: str = Form(""),
    token: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
):
    account = await get_crm_account_for_login(identifier or slug, slug or None)
    generic_message = (
        "Якщо акаунт кабінету знайдено, відкрийте Telegram-бот CarPot з акаунта власника "
        "та натисніть «Скинути пароль кабінету», щоб отримати захищене посилання."
    )

    if not account or not account["is_active"] or not account["crm_enabled"]:
        return _render_reset_password(
            request,
            slug=slug,
            identifier=identifier,
            message=generic_message,
        )

    account = dict(account)
    token_valid, token_error = verify_crm_password_reset_token(account, token)
    if not token_valid:
        return _render_reset_password(
            request,
            account=account,
            slug=account["crm_slug"],
            identifier=identifier or _seller_crm_login_value(account),
            message=generic_message if not token else None,
            error=token_error if token else None,
            status_code=400 if token else 200,
        )

    if password != password_confirm:
        return _render_reset_password(
            request,
            account=account,
            slug=account["crm_slug"],
            identifier=identifier or _seller_crm_login_value(account),
            token=token,
            token_verified=True,
            error="Паролі не співпадають.",
            status_code=400,
        )

    password_valid, password_error = validate_crm_password(password)
    if not password_valid:
        return _render_reset_password(
            request,
            account=account,
            slug=account["crm_slug"],
            identifier=identifier or _seller_crm_login_value(account),
            token=token,
            token_verified=True,
            error=password_error,
            status_code=400,
        )

    updated_account = await set_crm_password_hash_for_verified_reset(account["id"], hash_crm_password(password))
    logger.info(
        "CRM_PASSWORD_RESET seller_id=%s account_id=%s slug=%s",
        updated_account["seller_id"],
        updated_account["id"],
        updated_account["crm_slug"],
    )
    return RedirectResponse(url=f"/crm/seller/login?slug={updated_account['crm_slug']}", status_code=303)


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

    if not account.get("password_hash"):
        return RedirectResponse(url=f"/crm/seller/setup-password?slug={account['crm_slug']}", status_code=303)

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
    thread_status: str | None = None,
    thread_error: str | None = None,
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
            "meta": get_crm_lead_status_meta(tab["key"]),
            "active": tab["key"] == active_status,
            "href": f"/crm/seller/{crm_slug}/leads?status={tab['key']}",
        }
        for tab in LEAD_STATUS_TABS
    ]
    active_tab = next(tab for tab in tabs if tab["active"])
    if _is_demo_account(account):
        leads = []
    else:
        leads = _prepare_marketplace_leads(
            await list_seller_crm_marketplace_leads(
                account["seller_id"],
                status=active_status,
            ),
            active_status=active_status,
        )

    return templates.TemplateResponse(
        "seller_crm/leads.html",
        _seller_crm_context(
            request,
            title="Нові заявки — кабінет продавця CarPot",
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
            thread_status=thread_status,
            thread_error=thread_error,
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
    thread_status: str | None = None,
    thread_error: str | None = None,
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
        raise HTTPException(status_code=404, detail="Заявку не знайдено") from exc

    raw_lead_detail = await get_seller_crm_lead_detail(
        account["seller_id"],
        parsed_request_id,
    )
    if raw_lead_detail:
        raw_lead_detail["thread_messages"] = await list_lead_thread_messages(
            lead_id=parsed_request_id,
            seller_id=int(account["seller_id"]),
        )
        await mark_lead_thread_messages_read(
            lead_id=parsed_request_id,
            reader_role="seller",
            seller_id=int(account["seller_id"]),
        )
    lead_detail = _prepare_lead_detail(raw_lead_detail)
    if not lead_detail:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")

    return templates.TemplateResponse(
        "seller_crm/lead_detail.html",
        _seller_crm_context(
            request,
            title=f"Заявка #{parsed_request_id} — кабінет продавця CarPot",
            demo_mode=False,
            current_page="leads",
            account=account,
            subscription=subscription,
            lead=lead_detail,
            offer_status=offer_status,
            error=error,
            action_status=action_status,
            action_error=action_error,
            thread_status=thread_status,
            thread_error=thread_error,
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
        raise HTTPException(status_code=404, detail="Заявку не знайдено")

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
            repository_action = {
                SELLER_LEAD_ACTION_VIEWED: SELLER_LEAD_ACTION_VIEWED,
                SELLER_LEAD_ACTION_DECLINED: SELLER_LEAD_ACTION_DECLINED,
                SELLER_LEAD_ACTION_ARCHIVED: SELLER_LEAD_ACTION_ARCHIVED,
                SELLER_LEAD_ACTION_SKIPPED: SELLER_LEAD_ACTION_SKIPPED,
            }.get(action)
            if not repository_action:
                raise ValueError("Invalid CRM lead action")
            await mark_seller_lead_action(
                seller_id=seller_id,
                request_id=parsed_request_id,
                action=repository_action,
                metadata={"source": "seller_crm"},
            )
            if repository_action == SELLER_LEAD_ACTION_DECLINED:
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
    except Exception as exc:
        constraints = await get_seller_lead_action_constraints()
        logger.exception(
            "CRM seller lead action failed seller_id=%s request_id=%s action=%s db_constraints=%s exc=%s",
            seller_id,
            parsed_request_id,
            action,
            constraints,
            repr(exc),
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
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, SELLER_LEAD_ACTION_VIEWED, next_url)


@router.post("/{crm_slug}/leads/{request_id}/decline")
async def seller_crm_decline_lead(
    request: Request,
    crm_slug: str,
    request_id: str,
    next_url: str = Form(""),
):
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, SELLER_LEAD_ACTION_DECLINED, next_url)


@router.post("/{crm_slug}/leads/{request_id}/skip")
async def seller_crm_skip_lead(
    request: Request,
    crm_slug: str,
    request_id: str,
    next_url: str = Form(""),
):
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, SELLER_LEAD_ACTION_SKIPPED, next_url)


@router.post("/{crm_slug}/leads/{request_id}/reopen")
async def seller_crm_reopen_lead(
    request: Request,
    crm_slug: str,
    request_id: str,
    next_url: str = Form(""),
):
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, "reopened", next_url)



@router.post("/{crm_slug}/leads/{request_id}/archive")
async def seller_crm_archive_lead(
    request: Request,
    crm_slug: str,
    request_id: str,
    next_url: str = Form(""),
):
    return await _handle_seller_crm_lead_action(request, crm_slug, request_id, SELLER_LEAD_ACTION_ARCHIVED, next_url)

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
        raise HTTPException(status_code=404, detail="Заявку не знайдено")

    redirect_base = f"/crm/seller/{crm_slug}/leads/{parsed_request_id}"
    lead_detail = _prepare_lead_detail(
        await get_seller_crm_lead_detail(int(account["seller_id"]), parsed_request_id)
    )
    if not lead_detail:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")
    if not lead_detail.get("may_respond"):
        query = urlencode({"error": lead_detail.get("response_block_reason") or "Відповідь із CRM зараз недоступна."})
        return RedirectResponse(url=f"{redirect_base}?{query}", status_code=303)

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
    elif notification_status == NOTIFICATION_STATUS_SENT:
        status = NOTIFICATION_STATUS_SENT
    else:
        status = "saved"
    query = urlencode({"offer_status": status})
    return RedirectResponse(url=f"{redirect_base}?{query}", status_code=303)



def _crm_thread_title(context: dict[str, Any]) -> str:
    return " ".join(str(part).strip() for part in [context.get("brand"), context.get("model")] if part) or context.get("category") or "заявка CarPot"


def _format_seller_thread_reply(context: dict[str, Any], message_text: str) -> str:
    return "\n".join([escape(message_text.strip()[:1200])])


async def _handle_seller_thread_reply(
    request: Request,
    crm_slug: str,
    request_id: str,
    *,
    offer_id: str | None = None,
    message: str = "",
):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    try:
        parsed_request_id = int(request_id)
        parsed_offer_id = int(offer_id) if offer_id else None
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Діалог не знайдено") from exc

    redirect_url = f"/crm/seller/{crm_slug}/leads/{parsed_request_id}#thread"
    cleaned = (message or "").strip()
    if not cleaned:
        return RedirectResponse(url=_append_query(redirect_url, {"thread_error": "Додайте текст відповіді."}), status_code=303)

    if not await seller_has_crm_lead_access(int(account["seller_id"]), parsed_request_id):
        raise HTTPException(status_code=404, detail="Заявку не знайдено")

    context = await get_buyer_thread_delivery_context(
        lead_id=parsed_request_id,
        seller_id=int(account["seller_id"]),
        proposal_id=parsed_offer_id,
    )
    if not context or not context.get("buyer_telegram_id"):
        return RedirectResponse(url=_append_query(redirect_url, {"thread_error": "У покупця немає Telegram для доставки відповіді."}), status_code=303)

    buyer_telegram_id = int(context["buyer_telegram_id"])
    lead_title = _crm_thread_title(context)
    notify_text = f"Нове повідомлення по заявці {lead_title}"
    sent = None
    if not is_buyer_in_chat(buyer_telegram_id=buyer_telegram_id, lead_id=parsed_request_id):
        sent = await send_message_to_buyer(
            buyer_telegram_id,
            notify_text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Відкрити чат", callback_data=f"buyer_thread:open:{parsed_request_id}")]]
            ),
        )
    saved = await create_lead_thread_message(
        lead_id=parsed_request_id,
        proposal_id=parsed_offer_id or context.get("proposal_id"),
        sender_role=LEAD_THREAD_SENDER_SELLER,
        sender_id=int(account["seller_id"]),
        message_text=cleaned,
        read_state=LEAD_THREAD_READ_READ,
    )
    if sent and saved:
        await attach_telegram_delivery_to_thread_message(
            message_id=int(saved["id"]),
            telegram_chat_id=int(context["buyer_telegram_id"]),
            telegram_message_id=int(sent.message_id),
        )
        return RedirectResponse(url=_append_query(redirect_url, {"thread_status": "sent"}), status_code=303)

    return RedirectResponse(url=_append_query(redirect_url, {"thread_error": "Повідомлення збережено, але Telegram не підтвердив доставку."}), status_code=303)


@router.post("/{crm_slug}/leads/{request_id}/thread")
async def seller_crm_lead_thread_reply(
    request: Request,
    crm_slug: str,
    request_id: str,
    message: str = Form(""),
):
    return await _handle_seller_thread_reply(request, crm_slug, request_id, message=message)


@router.post("/{crm_slug}/offers/{offer_id}/thread")
async def seller_crm_offer_thread_reply(
    request: Request,
    crm_slug: str,
    offer_id: str,
    request_id: str = Form(""),
    message: str = Form(""),
):
    return await _handle_seller_thread_reply(request, crm_slug, request_id, offer_id=offer_id, message=message)

@router.get("/{crm_slug}/offers")
async def seller_crm_offers(request: Request, crm_slug: str, status: str = CRM_OFFER_STATUS_ACTIVE):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    active_status = status if status in ALLOWED_OFFER_STATUSES else CRM_OFFER_STATUS_ACTIVE
    tabs = [
        {
            **tab,
            "meta": get_crm_offer_status_meta(tab["key"]),
            "active": tab["key"] == active_status,
            "href": f"/crm/seller/{crm_slug}/offers?status={tab['key']}",
        }
        for tab in OFFER_STATUS_TABS
    ]
    active_tab = next(tab for tab in tabs if tab["active"])
    if _is_demo_account(account):
        offers = []
    else:
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
            title="Діалоги — кабінет продавця CarPot",
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
        raise HTTPException(status_code=404, detail="Пропозицію не знайдено") from exc

    raw_offer_detail = await get_seller_crm_offer_detail(
        account["seller_id"],
        parsed_offer_id,
    )
    if raw_offer_detail:
        raw_offer_detail["thread_messages"] = await list_lead_thread_messages(
            lead_id=int(raw_offer_detail["request"]["request_id"]),
            seller_id=int(account["seller_id"]),
            proposal_id=parsed_offer_id,
        )
        await mark_lead_thread_messages_read(
            lead_id=int(raw_offer_detail["request"]["request_id"]),
            reader_role="seller",
            seller_id=int(account["seller_id"]),
        )
    offer_detail = _prepare_offer_detail(raw_offer_detail)
    if not offer_detail:
        raise HTTPException(status_code=404, detail="Пропозицію не знайдено")

    return templates.TemplateResponse(
        "seller_crm/offer_detail.html",
        _seller_crm_context(
            request,
            title=f"Пропозиція #{parsed_offer_id} — кабінет продавця CarPot",
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
    if _is_demo_account(account):
        summary = _demo_content_summary()
        site = {"subdomain": DEMO_CRM_SLUG, "config_draft": {"modules": {"products": True}}, "config_live": {"modules": {"products": True}}}
    else:
        summary = dict(await get_seller_crm_content_summary(seller_id) or {})
        site = await get_site_by_seller(seller_id)
    account_flags = dict(account)
    draft_config = merge_with_default((site or {}).get("config_draft") or {}) if site else {}
    live_config = merge_with_default((site or {}).get("config_live") or {}) if site else {}
    products_module_draft_enabled = bool(((draft_config.get("modules") or {}).get("products", False)))
    products_module_live_enabled = bool(((live_config.get("modules") or {}).get("products", False)))
    has_website = bool(site or account_flags.get("has_site") or account_flags.get("website"))
    has_cars = int(summary.get("active_cars") or 0) > 0
    has_services = int(summary.get("active_services") or 0) > 0

    priority_sections = [
        {"key": "cars", "label": "Авто на розборі", "href": f"/crm/seller/{crm_slug}/content/cars"},
        {"key": "products", "label": "Запчастини / товари", "href": f"/crm/seller/{crm_slug}/content/products"},
        {"key": "services", "label": "Послуги", "href": f"/crm/seller/{crm_slug}/content/services"},
    ]

    return templates.TemplateResponse(
        "seller_crm/content.html",
        _seller_crm_context(
            request,
            title="Каталог — кабінет продавця CarPot",
            demo_mode=False,
            current_page="content",
            account=account,
            subscription=subscription,
            summary=summary,
            priority_sections=priority_sections,
            has_website=has_website,
            has_cars=has_cars,
            has_services=has_services,
            products_module_draft_enabled=products_module_draft_enabled,
            products_module_live_enabled=products_module_live_enabled,
        ),
    )

# Future products routes must keep this order:
# /content/products
# /content/products/import
# /content/products/import/template
# /content/products/create
# /content/products/{product_id}/edit
# /content/products/{product_id}
# /content/products/{product_id}/photo
# /content/products/{product_id}/enable
# /content/products/{product_id}/disable


@router.get("/{crm_slug}/content/products")
async def seller_crm_content_products(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    if _is_demo_account(account):
        summary = _demo_content_summary()
        products = []
    else:
        summary = dict(await get_seller_crm_content_summary(seller_id) or {})
        products = [dict(product) for product in await get_seller_products(seller_id, limit=100)]
    totals = {
        "active": sum(1 for product in products if product.get("status") == "active"),
        "quantity": sum(int(product.get("quantity") or 0) for product in products),
        "without_price": sum(1 for product in products if product.get("price") is None),
        "without_oem": sum(1 for product in products if not product.get("oem_code")),
    }

    return templates.TemplateResponse(
        "seller_crm/content_products.html",
        _seller_crm_context(
            request,
            title="Товари та запчастини — кабінет продавця CarPot",
            demo_mode=False,
            current_page="content_products",
            account=account,
            subscription=subscription,
            summary=summary,
            products=products,
            totals=totals,
            has_website=False,
            has_cars=int(summary.get("active_cars") or 0) > 0,
            has_services=int(summary.get("active_services") or 0) > 0,
        ),
    )


@router.get("/{crm_slug}/content/products/create")
async def seller_crm_product_create_form(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    donor_cars = [] if _is_demo_account(account) else [dict(car) for car in await get_seller_product_donor_cars(account["seller_id"])]
    return templates.TemplateResponse(
        "seller_crm/product_form.html",
        _seller_crm_context(
            request,
            title="Додати товар — кабінет продавця CarPot",
            demo_mode=False,
            current_page="content_products",
            account=account,
            subscription=subscription,
            form_title="Додати товар",
            form=_product_form_payload(status="active", stock_status="available", quantity="1"),
            error=None,
            action_url=f"/crm/seller/{crm_slug}/content/products/create",
            cancel_url=f"/crm/seller/{crm_slug}/content/products",
            donor_cars=donor_cars,
            stock_status_options=PRODUCT_STOCK_STATUS_OPTIONS,
            status_options=PRODUCT_STATUS_OPTIONS,
        ),
    )


@router.post("/{crm_slug}/content/products/create")
async def seller_crm_product_create(
    request: Request, crm_slug: str, title: str = Form(""), category: str = Form(""), brand: str = Form(""),
    model: str = Form(""), oem_code: str = Form(""), condition: str = Form(""), description: str = Form(""),
    price: str = Form(""), quantity: str = Form("1"), stock_status: str = Form("available"), status: str = Form("active"), donor_car_id: str = Form(""),
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    parsed_price, parsed_quantity, error = _validate_product_form(title, category, description, price, quantity, stock_status, status)
    donor_cars = [] if _is_demo_account(account) else [dict(car) for car in await get_seller_product_donor_cars(account["seller_id"])]
    donor_id = _parse_optional_int(donor_car_id)
    form = _product_form_payload(title=title, category=category, brand=brand, model=model, oem_code=oem_code, condition=condition, description=description, price=price, quantity=quantity, stock_status=stock_status, status=status, donor_car_id=donor_car_id)
    if error:
        return templates.TemplateResponse("seller_crm/product_form.html", _seller_crm_context(request, title="Додати товар — кабінет продавця CarPot", demo_mode=False, current_page="content_products", account=account, subscription=subscription, form_title="Додати товар", form=form, error=error, action_url=f"/crm/seller/{crm_slug}/content/products/create", cancel_url=f"/crm/seller/{crm_slug}/content/products", donor_cars=donor_cars, stock_status_options=PRODUCT_STOCK_STATUS_OPTIONS, status_options=PRODUCT_STATUS_OPTIONS), status_code=400)
    created = await create_product(seller_id=account["seller_id"], title=title, category=category, donor_car_id=donor_id, brand=brand, model=model, oem_code=oem_code, condition=condition, description=description, price=parsed_price, quantity=parsed_quantity, stock_status=stock_status, status=status)
    if not created:
        return templates.TemplateResponse("seller_crm/product_form.html", _seller_crm_context(request, title="Додати товар — кабінет продавця CarPot", demo_mode=False, current_page="content_products", account=account, subscription=subscription, form_title="Додати товар", form=form, error="Не вдалося створити товар. Перевірте поля.", action_url=f"/crm/seller/{crm_slug}/content/products/create", cancel_url=f"/crm/seller/{crm_slug}/content/products", donor_cars=donor_cars, stock_status_options=PRODUCT_STOCK_STATUS_OPTIONS, status_options=PRODUCT_STATUS_OPTIONS), status_code=400)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/products", status_code=303)


@router.get("/{crm_slug}/content/products/import")
async def seller_crm_product_import_form(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    return templates.TemplateResponse(
        "seller_crm/product_import.html",
        _seller_crm_context(
            request,
            title="Імпорт товарів — кабінет продавця CarPot",
            demo_mode=False,
            current_page="content_products",
            account=account,
            subscription=subscription,
            import_columns=PRODUCT_IMPORT_COLUMNS,
            result=None,
            error=None,
            has_website=False,
            has_cars=False,
            has_services=False,
        ),
    )


@router.post("/{crm_slug}/content/products/import")
async def seller_crm_product_import(
    request: Request,
    crm_slug: str,
    import_file: UploadFile = File(...),
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    content = await import_file.read()
    if not content:
        result = None
        error = "Оберіть CSV або XLSX файл для імпорту."
        status_code = 400
    else:
        result = await import_products_from_file(
            seller_id=account["seller_id"],
            filename=import_file.filename or "",
            content=content,
        )
        error = None
        status_code = 400 if result.validation_errors else 200

    return templates.TemplateResponse(
        "seller_crm/product_import.html",
        _seller_crm_context(
            request,
            title="Результат імпорту товарів — кабінет продавця CarPot",
            demo_mode=False,
            current_page="content_products",
            account=account,
            subscription=subscription,
            import_columns=PRODUCT_IMPORT_COLUMNS,
            result=result,
            error=error,
            has_website=False,
            has_cars=False,
            has_services=False,
        ),
        status_code=status_code,
    )


@router.get("/{crm_slug}/content/products/import/template")
async def seller_crm_product_import_template(request: Request, crm_slug: str, format: str = "csv"):
    try:
        await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    normalized_format = (format or "csv").strip().lower()
    if normalized_format == "xlsx":
        body = generate_product_import_xlsx_template()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "carpot_products_import_template.xlsx"
    else:
        body = generate_product_import_csv_template()
        media_type = "text/csv; charset=utf-8"
        filename = "carpot_products_import_template.csv"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    if _is_demo_account(account):
        summary = _demo_content_summary()
        services = []
    else:
        summary = dict(await get_seller_crm_content_summary(seller_id) or {})
        services = [dict(service) for service in await list_seller_crm_services_inventory(seller_id)]
    for service in services:
        detail = None if _is_demo_account(account) else await get_seller_service_detail(seller_id=seller_id, service_id=service["service_id"])
        if detail:
            status_meta = get_service_display_status(detail.get("is_active", True))
            service["status_supported"] = detail.get("status_supported", False)
            service["content_completeness"] = detail.get("content_completeness", 0)
        else:
            status_meta = get_service_display_status(True)
            service["status_supported"] = False
            service["content_completeness"] = 0
        service["status_meta"] = status_meta
        service["status_label"] = status_meta["label"]
        service["status_class"] = status_meta["css_class"]
        service["is_active"] = status_meta["is_active"]
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
    site = _demo_site() if _is_demo_account(account) else await get_current_seller_site_or_404(seller_id)
    account_flags = dict(account)
    has_website = bool(site or account_flags.get("has_site") or account_flags.get("website"))

    return templates.TemplateResponse(
        "seller_crm/content_services.html",
        _seller_crm_context(
            request,
            title="Послуги — кабінет продавця CarPot",
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
            title="Додати послугу — кабінет продавця CarPot",
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
                title="Додати послугу — кабінет продавця CarPot",
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
                title="Додати послугу — кабінет продавця CarPot",
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
            title="Редагувати послугу — кабінет продавця CarPot",
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
                title="Редагувати послугу — кабінет продавця CarPot",
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
            title=f"{service.get('title') or 'Послуга'} — кабінет продавця CarPot",
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


# Static route must be registered before dynamic {id} route.
@router.get("/{crm_slug}/content/cars")
async def seller_crm_content_cars(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    if _is_demo_account(account):
        summary = _demo_content_summary()
        cars = []
    else:
        summary = dict(await get_seller_crm_content_summary(seller_id) or {})
        cars = [dict(car) for car in await list_seller_crm_cars_inventory(seller_id)]
    for car in cars:
        status_meta = get_car_display_status(car.get("status"))
        car["status_meta"] = status_meta
        car["status_label"] = status_meta["label"]
        car["status_class"] = status_meta["css_class"]
        car["is_active"] = status_meta["is_active"]
        photo_id = car.get("photo_id") or ""
        car["photo_is_url"] = isinstance(photo_id, str) and photo_id.startswith(("http://", "https://"))
    if cars:
        part_counters = await get_parts_counters_by_car_ids(seller_id, [int(car.get("car_id")) for car in cars])
        for car in cars:
            counts = part_counters.get(int(car.get("car_id")), {"total": 0, "available": 0})
            car["parts_total"] = counts["total"]
            car["parts_available"] = counts["available"]
    totals = {
        "views": sum(int(car.get("views") or 0) for car in cars),
        "phone_clicks": sum(int(car.get("phone_clicks") or 0) for car in cars),
        "site_clicks": sum(int(car.get("site_clicks") or 0) for car in cars),
    }
    site = _demo_site() if _is_demo_account(account) else await get_current_seller_site_or_404(seller_id)
    account_flags = dict(account)
    has_website = bool(site or account_flags.get("has_site") or account_flags.get("website"))

    return templates.TemplateResponse(
        "seller_crm/content_cars.html",
        _seller_crm_context(
            request,
            title="Авто на розборі — кабінет продавця CarPot",
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
            title="Редагувати авто — кабінет продавця CarPot",
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
                title="Редагувати авто — кабінет продавця CarPot",
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
    counters = await get_parts_counters_by_car_ids(account["seller_id"], [car_id])
    counts = counters.get(car_id, {"total": 0, "available": 0})
    car["parts_total"] = counts["total"]
    car["parts_available"] = counts["available"]

    return templates.TemplateResponse(
        "seller_crm/car_detail.html",
        _seller_crm_context(
            request,
            title=f"{car.get('brand') or 'Авто'} {car.get('model') or ''} — кабінет продавця CarPot",
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


@router.post("/{crm_slug}/content/cars/{car_id}/photo")
async def seller_crm_car_photo_upload(
    request: Request,
    crm_slug: str,
    car_id: int,
    photo: UploadFile | None = File(None),
):
    detail_url = f"/crm/seller/{crm_slug}/content/cars/{car_id}"
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    car = await get_seller_crm_car_detail(account["seller_id"], car_id)
    if not car:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars?error=car_not_found", status_code=303)

    image_url, error_key = await _upload_validated_car_photo(photo)
    if error_key or not image_url:
        return RedirectResponse(url=f"{detail_url}?error={error_key or 'photo_upload_failed'}", status_code=303)

    saved = await update_seller_crm_car_photo(account["seller_id"], car_id, image_url)
    if not saved:
        return RedirectResponse(url=f"{detail_url}?error=photo_save_failed", status_code=303)

    return RedirectResponse(url=f"{detail_url}?status=photo_updated", status_code=303)


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


@router.post("/{crm_slug}/content/cars/{car_id}/delete")
async def seller_crm_car_delete(request: Request, crm_slug: str, car_id: int):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    if not await seller_owns_car(seller_id, car_id):
        raise HTTPException(status_code=403, detail="Access denied")

    archived = await archive_seller_car(seller_id=seller_id, car_id=car_id)
    if not archived:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars?status=car_deleted", status_code=303)

    await hide_parts_by_car(seller_id=seller_id, car_id=car_id)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars?status=car_deleted", status_code=303)


@router.post("/{crm_slug}/content/cars/{car_id}/generate-parts")
async def seller_crm_generate_parts(request: Request, crm_slug: str, car_id: int, publish_now: str | None = Form(None)):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    if not await seller_owns_car(seller_id, car_id):
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars?error=car_not_found", status_code=303)
    try:
        created_count = await generate_parts_for_car(seller_id, car_id)
        if created_count and publish_now in {"1", "true", "on", "yes"}:
            await update_generated_parts_status(seller_id, car_id, "available")
        status = "parts_created" if created_count else "parts_exists"
    except Exception:
        logger.exception("Failed to generate parts for seller_id=%s car_id=%s", seller_id, car_id)
        status = "parts_generate_failed"
    created_param = created_count if status == "parts_created" else 0
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts?status={status}&created={created_param}", status_code=303)


@router.get("/{crm_slug}/content/cars/{car_id}/parts")
async def seller_crm_car_parts(request: Request, crm_slug: str, car_id: int, status: str | None = None, error: str | None = None, q: str = "", part_status: str = "all", created: int = 0):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    seller_id = account["seller_id"]
    car = await get_seller_crm_car_detail(seller_id, car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    if not await seller_owns_car(seller_id, car_id):
        raise HTTPException(status_code=403, detail="Access denied")
    query_text = _normalize_part_search(q)
    normalized_status_filter = None if part_status == "all" else part_status
    if normalized_status_filter and normalized_status_filter not in VALID_PART_STATUSES:
        normalized_status_filter = None
    parts = [_prepare_part(item) for item in await get_parts_by_car_id_filtered(seller_id, car_id, normalized_status_filter, query_text or None)]
    category_rows = [dict(row) for row in await get_car_part_categories(car_id)]
    categories = []
    for row in category_rows:
        category_key = normalize_part_category(row.get("category"))
        categories.append(
            {"key": category_key, "label": PART_CATEGORY_LABELS.get(category_key, category_key), "total": row.get("total") or 0, "active": row.get("active") or 0}
        )
    stats = {
        "total": len(parts),
        "available": sum(1 for item in parts if item.get("status") == "available"),
        "draft": sum(1 for item in parts if item.get("status") == "draft"),
        "hidden": sum(1 for item in parts if item.get("status") == "hidden"),
        "sold": sum(1 for item in parts if item.get("status") == "sold"),
        "no_price": sum(1 for item in parts if item.get("price") is None),
        "no_photo": sum(1 for item in parts if not item.get("photo_id")),
        "no_description": sum(1 for item in parts if not (item.get("description") or "").strip()),
    }
    completeness_points = max(stats["total"] * 3, 1)
    completed_points = (
        (stats["total"] - stats["no_price"])
        + (stats["total"] - stats["no_photo"])
        + (stats["total"] - stats["no_description"])
    )
    stats["completion"] = int(round((completed_points / completeness_points) * 100))
    grouped_parts = {category: [] for category, _ in PART_CATEGORY_OPTIONS}
    for part in parts:
        category_key = normalize_part_category(part.get("category"))
        if category_key not in grouped_parts:
            category_key = "other"
        if not part.get("photo_id") and car.get("photo_id"):
            part["preview_photo"] = car.get("photo_id")
        grouped_parts[category_key].append(part)
    visible_count = sum(len(items) for items in grouped_parts.values())
    if visible_count != len(parts):
        logger.warning("Grouped parts count mismatch for seller_id=%s car_id=%s visible=%s total=%s", seller_id, car_id, visible_count, len(parts))
    site = await get_site_by_seller(seller_id)
    draft_config = merge_with_default((site or {}).get("config_draft") or {}) if site else {}
    live_config = merge_with_default((site or {}).get("config_live") or {}) if site else {}
    products_module_draft_enabled = bool(((draft_config.get("modules") or {}).get("products", False)))
    products_module_live_enabled = bool(((live_config.get("modules") or {}).get("products", False)))
    show_products_module_notice = bool(stats["available"] > 0 and (products_module_draft_enabled and not products_module_live_enabled or (not products_module_draft_enabled and not products_module_live_enabled)))
    return templates.TemplateResponse(
        "seller_crm/car_parts.html",
        _seller_crm_context(
            request,
            title="Запчастини авто — кабінет продавця CarPot",
            demo_mode=False,
            current_page="content_cars",
            account=account,
            subscription=subscription,
            car=car,
            parts=parts,
            grouped_parts=grouped_parts,
            categories=categories,
            stats=stats,
            status=status,
            error=error,
            part_status_labels=PART_STATUS_LABELS,
            category_options=PART_CATEGORY_OPTIONS,
            selected_part_status=part_status,
            q=query_text,
            created=created,
            show_products_module_notice=show_products_module_notice,
            products_module_draft_enabled=products_module_draft_enabled,
            products_module_live_enabled=products_module_live_enabled,
            has_website=False,
            has_cars=True,
            has_services=False,
        ),
    )


@router.post("/{crm_slug}/content/parts/{part_id}/status")
async def seller_crm_part_status_update(request: Request, crm_slug: str, part_id: int, status: str = Form("draft")):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != account["seller_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    if status not in VALID_PART_STATUSES:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts?error=invalid_status", status_code=303)
    await update_part_status(part_id, account["seller_id"], status)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts?status=part_status_updated", status_code=303)


@router.post("/{crm_slug}/content/parts/{part_id}/price")
async def seller_crm_part_price_update(
    request: Request,
    crm_slug: str,
    part_id: int,
    price: str = Form(""),
):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != account["seller_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    parsed_price, price_error = _parse_part_price(price)
    if price_error:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts?error=invalid_price", status_code=303)
    updated = await update_part_price(part_id, account["seller_id"], parsed_price)
    if not updated:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts?error=part_not_updated", status_code=303)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts?status=price_updated", status_code=303)


@router.post("/{crm_slug}/content/cars/{car_id}/parts/bulk-status")
async def seller_crm_parts_bulk_status(
    request: Request,
    crm_slug: str,
    car_id: int,
    category: str = Form(""),
    status: str = Form("draft"),
):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    if not await seller_owns_car(account["seller_id"], car_id):
        raise HTTPException(status_code=403, detail="Access denied")
    normalized_category = normalize_part_category(category)
    if normalized_category not in ALLOWED_PART_CATEGORIES or status not in VALID_PART_STATUSES:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts?error=invalid_bulk_params", status_code=303)
    await bulk_update_parts_status_by_category(account["seller_id"], car_id, normalized_category, status)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts?status=bulk_updated", status_code=303)


@router.get("/{crm_slug}/content/cars/{car_id}/parts/new")
async def seller_crm_part_create_form(request: Request, crm_slug: str, car_id: int):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    car = await get_seller_crm_car_detail(account["seller_id"], car_id)
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    return templates.TemplateResponse("seller_crm/part_edit.html", _seller_crm_context(
        request, title="Додати запчастину — кабінет продавця CarPot", current_page="content_cars", account=account, subscription=subscription,
        form_title="Додати запчастину вручну", action_url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts/new",
        cancel_url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts", car=car, form=_part_form_payload(),
        category_options=PART_CATEGORY_OPTIONS, status_options=list(PART_STATUS_LABELS.items()), error=None))


@router.post("/{crm_slug}/content/cars/{car_id}/parts/new")
async def seller_crm_part_create(
    request: Request, crm_slug: str, car_id: int, name: str = Form(""), category: str = Form("body"), status: str = Form("available"),
    price: str = Form(""), description: str = Form(""),
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
    normalized_name, parsed_price, validation_error = _validate_part_form(name, category, status, price, description)
    form = _part_form_payload(name=name, category=category, status=status, price=price, description=description)
    if validation_error:
        return templates.TemplateResponse("seller_crm/car_part_form.html", _seller_crm_context(
            request, title="Додати запчастину — кабінет продавця CarPot", current_page="content_cars", account=account, subscription=subscription,
            form_title="Додати запчастину вручну", action_url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts/new",
            cancel_url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts", car=car, form=form, category_options=PART_CATEGORY_OPTIONS,
            status_options=list(PART_STATUS_LABELS.items()), error=validation_error), status_code=400)
    normalized_category = normalize_part_category(category)
    created = await create_manual_part(account["seller_id"], car_id, normalized_category, normalized_name, status, parsed_price, (description or "").strip() or None)
    if not created:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts?error=part_duplicate", status_code=303)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{car_id}/parts?status=part_created", status_code=303)


@router.get("/{crm_slug}/content/parts/{part_id}/edit")
async def seller_crm_part_edit_form(request: Request, crm_slug: str, part_id: int):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != account["seller_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    car = await get_seller_crm_car_detail(account["seller_id"], part["car_id"])
    return templates.TemplateResponse("seller_crm/part_edit.html", _seller_crm_context(
        request, title="Редагувати запчастину — кабінет продавця CarPot", current_page="content_cars", account=account, subscription=subscription,
        form_title="Редагувати запчастину", action_url=f"/crm/seller/{crm_slug}/content/parts/{part_id}/edit",
        cancel_url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts", car=car,
        form=_part_form_payload(name=part.get("name"), category=part.get("category"), status=part.get("status"), price="" if part.get("price") is None else str(part.get("price")), description=part.get("description") or ""),
        category_options=PART_CATEGORY_OPTIONS, status_options=list(PART_STATUS_LABELS.items()), error=None,
        part=part, status_label=PART_STATUS_LABELS.get(part.get("status"), "Чернетка"), status_class=PART_STATUS_CLASSES.get(part.get("status"), "status-waiting")))


@router.post("/{crm_slug}/content/parts/{part_id}/edit")
async def seller_crm_part_edit(
    request: Request, crm_slug: str, part_id: int, name: str = Form(""), category: str = Form("body"), status: str = Form("available"),
    price: str = Form(""), description: str = Form(""),
):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != account["seller_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    car = await get_seller_crm_car_detail(account["seller_id"], part["car_id"])
    normalized_name, parsed_price, validation_error = _validate_part_form(name, category, status, price, description)
    form = _part_form_payload(name=name, category=category, status=status, price=price, description=description)
    if validation_error:
        return templates.TemplateResponse("seller_crm/part_edit.html", _seller_crm_context(
            request, title="Редагувати запчастину — кабінет продавця CarPot", current_page="content_cars", account=account, subscription=subscription,
            form_title="Редагувати запчастину", action_url=f"/crm/seller/{crm_slug}/content/parts/{part_id}/edit",
            cancel_url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts", car=car, form=form, category_options=PART_CATEGORY_OPTIONS,
            status_options=list(PART_STATUS_LABELS.items()), error=validation_error, part=part,
            status_label=PART_STATUS_LABELS.get(form.get("status"), "Чернетка"), status_class=PART_STATUS_CLASSES.get(form.get("status"), "status-waiting")), status_code=400)
    normalized_category = normalize_part_category(category)
    updated = await update_part_fields(part_id, account["seller_id"], normalized_name, normalized_category, status, parsed_price, (description or "").strip() or None)
    if not updated:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts?error=part_update_conflict", status_code=303)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/content/cars/{part['car_id']}/parts?status=part_updated", status_code=303)




@router.post("/{crm_slug}/content/parts/{part_id}/photo")
async def seller_crm_part_photo_upload(
    request: Request,
    crm_slug: str,
    part_id: int,
    photo: UploadFile | None = File(None),
):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != account["seller_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    detail_url = f"/crm/seller/{crm_slug}/content/parts/{part_id}/edit"
    image_url, error_key = await _upload_validated_car_photo(photo)
    if error_key or not image_url:
        return RedirectResponse(url=f"{detail_url}?error={error_key or 'photo_upload_failed'}", status_code=303)

    saved = await update_part_photo(part_id, account["seller_id"], image_url)
    if not saved:
        return RedirectResponse(url=f"{detail_url}?error=photo_save_failed", status_code=303)
    return RedirectResponse(url=f"{detail_url}?status=photo_updated", status_code=303)

@router.get("/{crm_slug}/settings")
async def seller_crm_settings(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    if _is_demo_account(account):
        settings_summary = _demo_settings_summary()
        content_summary = _demo_content_summary()
    else:
        settings_summary = await get_seller_crm_settings_summary(seller_id)
        if not settings_summary:
            raise HTTPException(status_code=404, detail="Seller settings not found")
        content_summary = dict(await get_seller_crm_content_summary(seller_id) or {})

    has_website = bool(settings_summary.get("site") or settings_summary.get("has_site"))

    return templates.TemplateResponse(
        "seller_crm/settings.html",
        _seller_crm_context(
            request,
            title="Налаштування та тарифи — кабінет продавця CarPot",
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


@router.post("/{crm_slug}/settings/site-package/{package_key}")
async def seller_crm_site_package_checkout(request: Request, crm_slug: str, package_key: str):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    package_map = {
        "standard": {"amount": 499, "product": "site_standard"},
        "plus": {"amount": 1499, "product": "site_plus"},
    }

    package = package_map.get(package_key)
    if not package:
        raise HTTPException(status_code=400, detail="Unknown site package")

    payment = await liqpay.create_payment(
        amount=package["amount"],
        server_url=LIQPAY_CALLBACK_URL,
        seller_id=account["seller_id"],
        product=package["product"],
    )
    return RedirectResponse(url=payment["url"], status_code=303)


@router.get("/{crm_slug}/profile")
async def seller_crm_profile(request: Request, crm_slug: str):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    if _is_demo_account(account):
        profile = _demo_public_profile()
        site = {"subdomain": "demo"}
    else:
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
    status = request.query_params.get("status")
    error = request.query_params.get("error")

    return templates.TemplateResponse(
        "seller_crm/profile.html",
        _seller_crm_context(
            request,
            title="Профіль продавця — кабінет CarPot",
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
            status=status,
            error=error,
        ),
    )


def _clean_optional(value: str | None, *, max_len: int) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    return normalized[:max_len]


def _normalize_website(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"
    return normalized[:255]


@router.post("/{crm_slug}/profile")
async def seller_crm_profile_update(
    request: Request,
    crm_slug: str,
    shop_name: str = Form(""),
    seller_name: str = Form(""),
    phone: str = Form(""),
    city: str = Form(""),
    website: str = Form(""),
    description: str = Form(""),
    photo: UploadFile | None = File(None),
):
    try:
        account, _subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    if _is_demo_account(account):
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/profile?error=demo_readonly", status_code=303)

    clean_phone = _clean_optional(phone, max_len=20)
    if clean_phone and not UA_PHONE_RE.match(clean_phone):
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/profile?error=invalid_phone", status_code=303)

    photo_url: str | None = None
    if photo and photo.filename:
        photo_url = await _upload_to_cloudinary(photo)
        if not photo_url:
            return RedirectResponse(url=f"/crm/seller/{crm_slug}/profile?error=photo_upload_failed", status_code=303)

    updated = await update_seller_crm_profile(
        int(account["seller_id"]),
        shop_name=_clean_optional(shop_name, max_len=120),
        seller_name=_clean_optional(seller_name, max_len=120),
        phone=clean_phone,
        city=_clean_optional(city, max_len=120),
        website=_normalize_website(website),
        description=_clean_optional(description, max_len=1200),
        photo_id=photo_url,
    )
    if not updated:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/profile?error=update_failed", status_code=303)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/profile?status=updated", status_code=303)


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
    if _is_demo_account(account):
        stats = _demo_analytics()
        marketplace_summary = {"new_requests": 3, "waiting_response": 2, "accepted_offers": 1, "avg_response_label": "18 хв"}
        marketplace_requests = []
        marketplace_activity = []
        leads = []
        cars = []
        services = []
        sources = [{"source": "telegram", "visits": 93}, {"source": "google", "visits": 71}, {"source": "direct", "visits": 22}]
        site = _demo_site()
    else:
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
            title="Кабінет продавця CarPot",
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
            products_module_draft_enabled=products_module_draft_enabled,
            products_module_live_enabled=products_module_live_enabled,
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
    if _is_demo_account(account):
        analytics = _demo_analytics()
    else:
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

    if _is_demo_account(account):
        site = _demo_site()
        cars = []
        services = []
    else:
        site = await get_site_by_seller(seller_id)
        cars = await list_seller_crm_cars(seller_id, limit=1)
        services = await list_seller_crm_services(seller_id, limit=1)
    account_flags = dict(account)
    has_website = bool(site or analytics.get("has_website") or account_flags.get("has_site") or account_flags.get("website"))

    return templates.TemplateResponse(
        "seller_crm/analytics.html",
        _seller_crm_context(
            request,
            title="Аналітика та статистика — кабінет продавця",
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
    site = _demo_site() if _is_demo_account(account) else await get_current_seller_site_or_404(seller_id)
    if not site:
        return templates.TemplateResponse(
            "seller_crm/website.html",
            _seller_crm_context(
                request,
                title="Сайт не налаштовано — кабінет продавця",
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

    config_draft = _as_config(site)
    config_live = _as_live_config(site)
    if _is_demo_account(account):
        services = []
        cars = []
        available_products_count = 0
        products_without_price_count = 0
        available_parts_count = 0
    else:
        services = [dict(row) for row in await get_services_by_seller(seller_id)]
        cars = [dict(row) for row in await get_cars_by_seller(seller_id)]
        seller_products = [dict(row) for row in await get_seller_products(seller_id, limit=500)]
        available_products_count = sum(1 for item in seller_products if item.get("status") == "active" and item.get("stock_status") == "available")
        products_without_price_count = sum(1 for item in seller_products if item.get("status") == "active" and item.get("stock_status") == "available" and item.get("price") is None)
        available_parts = [dict(row) for row in await get_available_parts_for_site(seller_id)]
        available_parts_count = len(available_parts)
    if _is_demo_account(account):
        brands = []
        models = []
    else:
        brands = await get_brands_with_ids()
        selected_brand = brands[0]["id"] if brands else None
        models = await get_models_by_brand_id(selected_brand) if selected_brand else []
    live_url = build_site_url(site["subdomain"])
    media = _collect_media(config_draft, services, cars)
    draft_products_enabled = bool(((config_draft.get("modules") or {}).get("products", False)))
    live_products_enabled = bool(((config_live.get("modules") or {}).get("products", False)))
    if live_products_enabled:
        catalog_module_message = "Модуль ‘Товари / запчастини’ увімкнений на сайті."
    elif draft_products_enabled:
        catalog_module_message = "Модуль увімкнений у чернетці. Опублікуйте сайт."
    else:
        catalog_module_message = "Модуль вимкнений у чернетці."

    return templates.TemplateResponse(
        "seller_crm/website.html",
        _seller_crm_context(
            request,
            title="Керування сайтом — кабінет продавця",
            current_page="website",
            account=account,
            subscription=subscription,
            site=site,
            has_website=True,
            has_cars=bool(cars),
            has_services=bool(services),
            config=config_draft,
            config_draft=config_draft,
            config_live=config_live,
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
            catalog_status={
                "draft_enabled": draft_products_enabled,
                "live_enabled": live_products_enabled,
                "module_message": catalog_module_message,
                "available_total": int(available_products_count + available_parts_count),
                "without_price": int(products_without_price_count),
            },
        ),
    )


@router.get("/{crm_slug}/website/editor")
async def seller_crm_website_editor(request: Request, crm_slug: str, status: str | None = None):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise

    seller_id = account["seller_id"]
    site = _demo_site() if _is_demo_account(account) else await get_current_seller_site_or_404(seller_id)
    config_draft = _as_config(site)
    blocks = [{"key": k, "title": v["name"], "description": v["description"], "shown": bool((config_draft.get("modules") or {}).get(k, False))} for k, v in WEBSITE_EDITABLE_BLOCKS.items()]
    return templates.TemplateResponse("seller_crm/website_editor.html", _seller_crm_context(request, title="Редагування сайту — кабінет продавця", current_page="website_editor", account=account, subscription=subscription, site=site, blocks=blocks, status=status, has_website=True, has_cars=False, has_services=False))


@router.get("/{crm_slug}/website/editor/{block_key}")
async def seller_crm_website_block_editor(request: Request, crm_slug: str, block_key: str):
    account, subscription = await _authorized_account(request, crm_slug)
    if block_key not in WEBSITE_EDITABLE_BLOCKS:
        raise HTTPException(status_code=400, detail="Невідомий блок")
    site = await get_current_seller_site_or_404(account["seller_id"])
    config_draft = _as_config(site)
    return templates.TemplateResponse(
        "seller_crm/website_block_edit.html",
        _seller_crm_context(
            request,
            title=f"Редагування блоку: {WEBSITE_EDITABLE_BLOCKS[block_key]['name']} — кабінет продавця",
            current_page="website_editor",
            account=account,
            subscription=subscription,
            site=site,
            block_key=block_key,
            block_name=WEBSITE_EDITABLE_BLOCKS[block_key]["name"],
            block_description=WEBSITE_EDITABLE_BLOCKS[block_key]["description"],
            config=config_draft,
            has_website=True,
            has_cars=False,
            has_services=False,
        ),
    )


@router.post("/{crm_slug}/website/editor/{block_key}")
async def seller_crm_website_block_editor_save(
    request: Request,
    crm_slug: str,
    block_key: str,
    enabled: str | None = Form(None),
):
    account, _ = await _authorized_account(request, crm_slug)
    if block_key not in WEBSITE_EDITABLE_BLOCKS:
        raise HTTPException(status_code=400, detail="Невідомий блок")

    form = await request.form()
    patch: dict[str, Any] = {"modules": {block_key: bool(enabled)}}

    if block_key == "hero":
        patch["hero"] = {
            "title": str(form.get("title") or "").strip(),
            "subtitle": str(form.get("subtitle") or "").strip(),
            "button_text": str(form.get("button_text") or "").strip(),
            "button_secondary_text": str(form.get("button_secondary_text") or "").strip(),
            "banners": _split_lines(str(form.get("banners") or "")),
        }
    elif block_key == "about":
        patch["about"] = {"title": str(form.get("title") or "").strip(), "text": str(form.get("text") or "").strip()}
    elif block_key == "contacts":
        patch["contacts"] = {
            "phones": _split_lines(str(form.get("phone") or "")),
            "address": str(form.get("address") or "").strip(),
            "messengers": {
                "telegram": str(form.get("telegram") or "").strip(),
                "viber": str(form.get("viber") or "").strip(),
                "whatsapp": str(form.get("whatsapp") or "").strip(),
            },
        }
    elif block_key == "map":
        patch["map"] = {"address": str(form.get("address") or "").strip()}
        patch["contacts"] = {"map_embed": str(form.get("map_embed") or "").strip()}
    elif block_key == "footer":
        patch["footer"] = {
            "text": str(form.get("text") or "").strip(),
            "copyright": str(form.get("copyright") or "").strip(),
        }
    elif block_key in {"cars", "products", "services"}:
        patch[block_key] = {
            "title": str(form.get("title") or "").strip(),
            "subtitle": str(form.get("subtitle") or "").strip(),
        }

    await update_current_site_draft(account["seller_id"], patch)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/website/editor?status=saved", status_code=303)

@router.get("/{crm_slug}/website/settings")
async def seller_crm_website_settings(request: Request, crm_slug: str, status: str | None = None):
    try:
        account, subscription = await _authorized_account(request, crm_slug)
    except HTTPException as exc:
        if exc.status_code == 303:
            return RedirectResponse(url=exc.detail, status_code=303)
        raise
    seller_id = account["seller_id"]
    site = _demo_site() if _is_demo_account(account) else await get_current_seller_site_or_404(seller_id)
    return templates.TemplateResponse("seller_crm/website_settings.html", _seller_crm_context(request, title="Налаштування сайту — кабінет продавця", current_page="website_settings", account=account, subscription=subscription, site=site, config=_as_config(site), themes=get_theme_presets(), status=status, has_website=True, has_cars=False, has_services=False))


@router.post("/{crm_slug}/website/editor/toggle/{module_key}")
async def toggle_website_block(request: Request, crm_slug: str, module_key: str):
    account, _ = await _authorized_account(request, crm_slug)
    allowed_keys = {"hero", "about", "cars", "products", "services", "gallery", "contacts", "map", "footer"}
    if module_key not in allowed_keys:
        raise HTTPException(status_code=400, detail="Невідомий блок")
    site = await get_current_seller_site_or_404(account["seller_id"])
    current_modules = (_as_config(site).get("modules") or {})
    next_value = not bool(current_modules.get(module_key, False))
    await update_current_site_draft(account["seller_id"], {"modules": {module_key: next_value}})
    form = await request.form()
    return_to = str(form.get("return_to") or "").strip()
    if return_to.startswith("/site/") and "\n" not in return_to and "\r" not in return_to:
        return RedirectResponse(url=return_to, status_code=303)
    return RedirectResponse(url=f"/crm/seller/{crm_slug}/website/editor?status=saved", status_code=303)


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
    await update_current_site_draft(
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
        await update_current_site_draft(account["seller_id"], {"header": {"logo": url}})
    return _redirect(crm_slug, "logo")


@router.post("/{crm_slug}/website/theme")
async def update_theme(request: Request, crm_slug: str, theme: str = Form("default")):
    account, _ = await _authorized_account(request, crm_slug)
    presets = get_theme_presets()
    preset = presets.get(theme, presets["default"])
    await update_current_site_draft(account["seller_id"], {"theme": {"scheme": preset["scheme"], "preset": theme, "accent": preset["accent"]}})
    return _redirect(crm_slug, "theme")


@router.post("/{crm_slug}/website/modules")
async def update_modules(request: Request, crm_slug: str):
    account, _ = await _authorized_account(request, crm_slug)
    form = await request.form()

    site = await get_site_by_seller(account["seller_id"])
    if not site:
        return RedirectResponse(url=f"/crm/seller/{crm_slug}/website?status=error", status_code=303)
    config_draft = site.get("config_draft") if site else {}
    existing_config = merge_with_default(config_draft or {})

    new_modules = {key: key in form for key, _ in MODULE_KEYS}
    existing_config["modules"] = {
        **(existing_config.get("modules") or {}),
        **new_modules,
    }

    await update_current_site_draft(account["seller_id"], existing_config)
    return RedirectResponse(
        url=f"/crm/seller/{crm_slug}/website?status=saved#modules-section",
        status_code=303,
    )


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
    await update_current_site_draft(account["seller_id"], {"hero": {"banners": _split_lines(banners)}})
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
    await update_current_site_draft(account["seller_id"], {"gallery": {"images": items}})
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
    await update_current_site_draft(account["seller_id"], {"pricing": {"items": items}})
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
    await publish_current_site(account["seller_id"])
    return _redirect(crm_slug, "publish", "published")


@router.get("/{crm_slug}/website/preview")
async def preview_draft_site(request: Request, crm_slug: str):
    account, _ = await _authorized_account(request, crm_slug)
    site = _demo_site() if _is_demo_account(account) else await get_site_by_seller(account["seller_id"])
    if not site:
        return HTMLResponse(
            "<h1>Сайт ще не налаштовано</h1><p>Поверніться до кабінету продавця та налаштуйте сайт.</p>",
            status_code=200,
        )
    config = _as_config(site)
    return templates.TemplateResponse(
        "site.html",
        {
            "request": request,
            "subdomain": site["subdomain"],
            "site_id": site.get("id"),
            "config": config,
            "seller": account,
            "cars": [] if _is_demo_account(account) else [dict(row) for row in await get_cars_by_seller(account["seller_id"])],
            "services": [] if _is_demo_account(account) else [dict(row) for row in await get_services_by_seller(account["seller_id"])],
            "products": config.get("products", {}),
        },
    )
    normalize_part_category,
