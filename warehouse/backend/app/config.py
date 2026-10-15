import os
from functools import lru_cache
from pathlib import Path
from sqlalchemy.engine import make_url, URL
from urllib.parse import urlsplit


@lru_cache
def database_url() -> str:
    value = os.environ.get("WAREHOUSE_DATABASE_URL", "")
    if not value and os.getenv("WAREHOUSE_DB_HOST"):
        names = [
            "WAREHOUSE_DB_HOST",
            "WAREHOUSE_DB_NAME",
            "WAREHOUSE_DB_USER",
            "WAREHOUSE_DB_PASSWORD",
        ]
        if any(not os.getenv(name) for name in names):
            raise RuntimeError("All Warehouse DB component variables are required")
        value = URL.create(
            "postgresql+psycopg",
            username=os.environ["WAREHOUSE_DB_USER"],
            password=os.environ["WAREHOUSE_DB_PASSWORD"],
            host=os.environ["WAREHOUSE_DB_HOST"],
            port=int(os.getenv("WAREHOUSE_DB_PORT", "5432")),
            database=os.environ["WAREHOUSE_DB_NAME"],
        ).render_as_string(hide_password=False)
    if not value:
        raise RuntimeError(
            "WAREHOUSE_DATABASE_URL is required; never reuse CarPot DATABASE_URL"
        )
    url = make_url(value)
    if url.drivername != "postgresql+psycopg" or not (url.database or "").startswith(
        ("warehouse", "carpot_warehouse")
    ):
        raise RuntimeError(
            "Use a separate PostgreSQL database named warehouse* or carpot_warehouse*"
        )
    return value


def secure_cookies() -> bool:
    return os.getenv("WAREHOUSE_COOKIE_SECURE", "true").lower() == "true"


def photo_dir() -> Path | None:
    value = os.getenv("WAREHOUSE_PHOTO_DIR")
    return Path(value).resolve() if value else None


def is_staging():
    return os.getenv("WAREHOUSE_ENV") == "staging"


def public_origin():
    value = os.getenv("WAREHOUSE_PUBLIC_ORIGIN", "")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or value != value.lower()
        or parsed.hostname.endswith(".")
        or not 1 <= (parsed.port or 443) <= 65535
    ):
        raise RuntimeError(
            "WAREHOUSE_PUBLIC_ORIGIN must be an exact lowercase HTTPS origin without path or trailing slash"
        )
    return value


def registration_enabled():
    return (
        os.getenv(
            "WAREHOUSE_REGISTRATION_ENABLED", "false" if is_staging() else "true"
        ).lower()
        == "true"
    )
