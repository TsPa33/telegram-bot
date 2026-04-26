import re
from typing import Awaitable, Callable

_ALLOWED_CHARS_PATTERN = re.compile(r"[^a-z0-9-]+")
_VALID_SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9-]{3,20}$")
_MULTIPLE_HYPHENS_PATTERN = re.compile(r"-{2,}")


def normalize_subdomain(value: str) -> str:
    """Normalize user input into a subdomain-safe slug."""
    if not value:
        return ""

    normalized = value.strip().lower().replace(" ", "-")
    normalized = _ALLOWED_CHARS_PATTERN.sub("", normalized)
    normalized = _MULTIPLE_HYPHENS_PATTERN.sub("-", normalized)

    return normalized


def is_valid_subdomain(value: str) -> bool:
    """Check whether the subdomain matches all project rules."""
    if not value:
        return False

    if not _VALID_SUBDOMAIN_PATTERN.fullmatch(value):
        return False

    if value.startswith("-") or value.endswith("-"):
        return False

    if "--" in value:
        return False

    return True


async def generate_unique_subdomain(
    base: str,
    exists_func: Callable[[str], Awaitable[bool]],
) -> str:
    """Generate a unique subdomain using incremental numeric suffixes."""
    normalized_base = normalize_subdomain(base)

    if is_valid_subdomain(normalized_base) and not await exists_func(normalized_base):
        return normalized_base

    candidate_base = normalized_base.strip("-")

    if not candidate_base:
        candidate_base = "site"

    candidate_base = candidate_base[:20]

    if not candidate_base:
        candidate_base = "site"

    if is_valid_subdomain(candidate_base) and not await exists_func(candidate_base):
        return candidate_base

    # Keep generating candidates until one is available.
    suffix = 1
    while True:
        suffix_str = str(suffix)
        max_base_len = 20 - (len(suffix_str) + 1)

        if max_base_len < 1:
            candidate = suffix_str[-20:]
        else:
            trimmed_base = candidate_base[:max_base_len].rstrip("-")
            if not trimmed_base:
                trimmed_base = "site"[:max_base_len] or "s"
            candidate = f"{trimmed_base}-{suffix_str}"

        if is_valid_subdomain(candidate) and not await exists_func(candidate):
            return candidate

        suffix += 1
