import base64
import hashlib
import hmac
import os
import re
import time
from typing import Any

from passlib.context import CryptContext

from bot.database.repositories.seller_crm_repo import (
    ensure_free_crm_account,
    get_crm_account_by_seller,
)

SELLER_CRM_PRODUCT = "seller_crm"
SELLER_CRM_MONTHLY_PRICE_UAH = int(os.getenv("SELLER_CRM_MONTHLY_PRICE_UAH", "99"))
SELLER_CRM_SUBSCRIPTION_DAYS = 30
SELLER_CRM_PASSWORD_MIN_LENGTH = 8
SELLER_CRM_SESSION_DAYS = 7
SELLER_CRM_PASSWORD_RESET_TTL_SECONDS = 30 * 60
SELLER_CRM_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])?$")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def normalize_crm_slug(value: str | None) -> str:
    value = (value or "").strip().lower()
    value = value.replace("_", "-")
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:40]


def validate_crm_slug(value: str | None) -> tuple[bool, str]:
    slug = normalize_crm_slug(value)
    if not slug:
        return False, "Введіть короткий CRM slug, наприклад sto-kyiv"
    if not SELLER_CRM_SLUG_RE.match(slug):
        return False, "Slug має містити 3–40 символів: латиниця, цифри та дефіс"
    if slug in {"admin", "api", "login", "logout", "demo", "seller", "crm", "www"}:
        return False, "Цей slug зарезервований. Оберіть інший"
    return True, slug


def validate_crm_password(password: str | None) -> tuple[bool, str]:
    password = password or ""
    if len(password) < SELLER_CRM_PASSWORD_MIN_LENGTH:
        return False, f"Пароль має містити мінімум {SELLER_CRM_PASSWORD_MIN_LENGTH} символів"
    if len(password.encode("utf-8")) > 72:
        return False, "Пароль занадто довгий для безпечного хешування"
    if password.isdigit() or password.isalpha():
        return False, "Додайте до пароля літери й цифри для кращого захисту"
    return True, ""


def _password_reset_secret() -> bytes:
    secret = os.getenv("SELLER_CRM_PASSWORD_RESET_SECRET") or os.getenv("BOT_TOKEN") or os.getenv("SECRET_KEY")
    if not secret:
        secret = "carpot-seller-crm-password-reset"
    return secret.encode("utf-8")


def _sign_password_reset_payload(payload: str) -> str:
    return hmac.new(_password_reset_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_crm_password_reset_token(account: dict[str, Any], ttl_seconds: int = SELLER_CRM_PASSWORD_RESET_TTL_SECONDS) -> str:
    expires_at = int(time.time()) + ttl_seconds
    password_fingerprint = hashlib.sha256(str(account.get("password_hash") or "").encode("utf-8")).hexdigest()
    payload = f"{account['id']}:{account['seller_id']}:{expires_at}:{password_fingerprint}"
    signature = _sign_password_reset_payload(payload)
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def verify_crm_password_reset_token(account: dict[str, Any], token: str | None) -> tuple[bool, str]:
    if not token:
        return False, "Підтвердіть скидання пароля через Telegram-акаунт власника."

    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        account_id, seller_id, expires_at, password_fingerprint, signature = decoded.rsplit(":", 4)
    except Exception:
        return False, "Посилання для скидання пароля некоректне або застаріле."

    payload = f"{account_id}:{seller_id}:{expires_at}:{password_fingerprint}"
    expected_signature = _sign_password_reset_payload(payload)
    if not hmac.compare_digest(signature, expected_signature):
        return False, "Посилання для скидання пароля некоректне або застаріле."

    if str(account.get("id")) != account_id or str(account.get("seller_id")) != seller_id:
        return False, "Посилання не належить цьому CRM акаунту."

    try:
        expires_at_timestamp = int(expires_at)
    except ValueError:
        return False, "Посилання для скидання пароля некоректне або застаріле."

    if expires_at_timestamp < int(time.time()):
        return False, "Термін дії посилання минув. Запитайте нове посилання у Telegram-боті."

    current_fingerprint = hashlib.sha256(str(account.get("password_hash") or "").encode("utf-8")).hexdigest()
    if not hmac.compare_digest(password_fingerprint, current_fingerprint):
        return False, "Це посилання вже використане або пароль було змінено."

    return True, ""


def hash_crm_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_crm_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return pwd_context.verify(password, password_hash)


def crm_slug_base_from_seller(seller: dict | None) -> str:
    seller = seller or {}
    for value in (seller.get("shop_name"), seller.get("username")):
        slug = normalize_crm_slug(value)
        if slug and slug not in {"admin", "api", "login", "logout", "demo", "seller", "crm", "www"}:
            return slug
    seller_id = seller.get("id")
    return normalize_crm_slug(f"seller-{seller_id}") if seller_id else "seller"


async def ensure_crm_credentials(seller: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Ensure a seller has a CRM account without creating a password.

    First-password onboarding is completed by the seller in the web CRM setup
    flow. This helper intentionally never generates or overwrites password
    hashes; it only reports whether setup is still required.
    """

    account, _created = await ensure_free_crm_account(
        seller_id=seller["id"],
        base_slug=crm_slug_base_from_seller(dict(seller)),
        password_hash="",
    )

    refreshed_account = await get_crm_account_by_seller(seller["id"])
    account = dict(refreshed_account or account)
    return account, not bool(account.get("password_hash"))
