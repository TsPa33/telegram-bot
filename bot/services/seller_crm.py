import os
import re
import secrets
import string
from typing import Any

from passlib.context import CryptContext

from bot.database.repositories.seller_crm_repo import (
    ensure_free_crm_account,
    get_crm_account_by_seller,
    set_crm_password_hash_if_empty,
)

SELLER_CRM_PRODUCT = "seller_crm"
SELLER_CRM_MONTHLY_PRICE_UAH = int(os.getenv("SELLER_CRM_MONTHLY_PRICE_UAH", "99"))
SELLER_CRM_SUBSCRIPTION_DAYS = 30
SELLER_CRM_PASSWORD_MIN_LENGTH = 8
SELLER_CRM_SESSION_DAYS = 7
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


def hash_crm_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_crm_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return pwd_context.verify(password, password_hash)


def generate_crm_temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        valid, _ = validate_crm_password(password)
        if valid:
            return password


def crm_slug_base_from_seller(seller: dict | None) -> str:
    seller = seller or {}
    for value in (seller.get("shop_name"), seller.get("username")):
        slug = normalize_crm_slug(value)
        if slug and slug not in {"admin", "api", "login", "logout", "demo", "seller", "crm", "www"}:
            return slug
    seller_id = seller.get("id")
    return normalize_crm_slug(f"seller-{seller_id}") if seller_id else "seller"


async def ensure_crm_credentials(seller: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Ensure a seller has a CRM account and one-time initial credentials.

    Returns the CRM account and a temporary password only when this call safely
    creates the first password hash. Existing password hashes are never
    overwritten, so repeated onboarding opens do not regenerate passwords.
    """

    account, _created = await ensure_free_crm_account(
        seller_id=seller["id"],
        base_slug=crm_slug_base_from_seller(dict(seller)),
        password_hash="",
    )

    if account.get("password_hash"):
        return dict(account), None

    temporary_password = generate_crm_temp_password()
    updated_account = await set_crm_password_hash_if_empty(
        account["id"],
        hash_crm_password(temporary_password),
    )
    if updated_account:
        return dict(updated_account), temporary_password

    refreshed_account = await get_crm_account_by_seller(seller["id"])
    return dict(refreshed_account or account), None
