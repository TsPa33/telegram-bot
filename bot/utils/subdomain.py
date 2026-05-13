import re
from typing import Awaitable, Callable

from bot.services.domain_service import validate_subdomain

_ALLOWED_CHARS_PATTERN = re.compile(r"[^a-z0-9-]+")
_MULTIPLE_HYPHENS_PATTERN = re.compile(r"-{2,}")


def normalize_subdomain(value: str) -> str:
    """Normalize user input into a subdomain-safe slug."""
    if not value:
        return ""

    normalized = value.strip().lower().replace(" ", "-")
    normalized = _ALLOWED_CHARS_PATTERN.sub("", normalized)
    normalized = _MULTIPLE_HYPHENS_PATTERN.sub("-", normalized)

    # FIX: remove leading/trailing hyphens
    normalized = normalized.strip("-")

    return normalized


def is_valid_subdomain(value: str) -> bool:
    """Check whether the subdomain matches public domain rules."""
    return validate_subdomain(value)


async def generate_unique_subdomain(
    base: str,
    exists_func: Callable[[str], Awaitable[bool]],
) -> str:
    """Generate a unique subdomain using incremental numeric suffixes."""
    normalized_base = normalize_subdomain(base)

    # fast path
    if is_valid_subdomain(normalized_base) and not await exists_func(normalized_base):
        return normalized_base

    candidate_base = normalized_base.strip("-") or "site"
    candidate_base = candidate_base[:32] or "site"

    if is_valid_subdomain(candidate_base) and not await exists_func(candidate_base):
        return candidate_base

    suffix = 1
    while True:
        suffix_str = str(suffix)
        max_base_len = 32 - (len(suffix_str) + 1)

        if max_base_len < 1:
            candidate = suffix_str[-32:]
        else:
            trimmed_base = candidate_base[:max_base_len].rstrip("-") or "s"
            candidate = f"{trimmed_base}-{suffix_str}"

        if is_valid_subdomain(candidate) and not await exists_func(candidate):
            return candidate

        suffix += 1
