import os
import re
import secrets
import string

from passlib.context import CryptContext

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
