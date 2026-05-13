import re

PUBLIC_SITE_DOMAIN = "carpot.com.ua"
PUBLIC_SITE_SCHEME = "https"
RESERVED_SUBDOMAINS = {
    "www",
    "admin",
    "api",
    "crm",
    "mail",
    "ftp",
    "dev",
    "test",
    "app",
    "cdn",
    "root",
    "support",
}

_SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9-]{3,32}$")


def normalize_subdomain(value: str | None) -> str:
    """Trim and lowercase a seller-provided subdomain without slugifying it."""
    if not value:
        return ""

    return value.strip().lower()


def validate_subdomain(value: str | None) -> bool:
    """Validate public seller subdomains for wildcard DNS routing."""
    raw_value = value or ""
    subdomain = normalize_subdomain(raw_value)

    if raw_value != subdomain:
        return False

    if subdomain in RESERVED_SUBDOMAINS:
        return False

    if "." in subdomain:
        return False

    if subdomain.endswith((".com", ".ua", ".com.ua")):
        return False

    return _SUBDOMAIN_PATTERN.fullmatch(subdomain) is not None


def build_site_url(subdomain: str | None) -> str:
    """Build the canonical public URL for a seller site."""
    normalized = normalize_subdomain(subdomain)
    return f"{PUBLIC_SITE_SCHEME}://{normalized}.{PUBLIC_SITE_DOMAIN}"


def extract_subdomain_from_host(host: str | None) -> str | None:
    """Extract a seller subdomain from the configured production wildcard host.

    Infrastructure is expected to route *.carpot.com.ua to the app via
    Cloudflare wildcard DNS and a Railway wildcard domain. Localhost,
    Railway preview domains, and the apex marketing domain are ignored.
    """
    if not host:
        return None

    hostname = host.split(":", 1)[0].strip().lower().rstrip(".")
    suffix = f".{PUBLIC_SITE_DOMAIN}"

    if hostname == PUBLIC_SITE_DOMAIN or hostname == f"www.{PUBLIC_SITE_DOMAIN}":
        return None

    if not hostname.endswith(suffix):
        return None

    subdomain = hostname[: -len(suffix)]

    if "." in subdomain:
        return None

    if not validate_subdomain(subdomain):
        return None

    return subdomain
