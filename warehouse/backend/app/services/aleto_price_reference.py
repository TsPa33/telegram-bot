"""Read-only indicative averages; never consumed by seller-price decisions."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit


def _aleto_url(value):
    try:
        u = urlsplit(value or "")
        return (u.scheme == "https" and u.hostname in ("aleto.ua", "www.aleto.ua")
                and u.port in (None, 443) and not u.username and not u.password)
    except ValueError:
        return False


def summarize_aleto(matches, *, truncated=False):
    """Summarize complete, already matched recent observations, not the UI sample.

    The caller has removed stale prices and hard model/position conflicts.
    Exact and similar matches are separate; currency and condition never mix.
    """
    if truncated:
        return []
    groups = defaultdict(dict)
    for match in matches:
        if match.get("conflict"):
            continue
        e = match["entry"]
        if str(e.get("source", "")).strip().casefold() != "aleto" or not _aleto_url(e.get("url")):
            continue
        if e.get("status") == "historical_not_recommendation":
            continue
        currency, condition = e.get("currency"), e.get("condition", "unknown")
        if currency not in ("UAH", "USD") or not e.get("article"):
            continue
        try:
            amount = Decimal(e["amount"])
            if not amount.is_finite() or amount <= 0:
                continue
        except (InvalidOperation, TypeError, KeyError):
            continue
        kind = "exact" if match["exact"] else "similar"
        groups[currency, condition, kind][str(e["article"])] = (amount, e)
    result = []
    for (currency, condition, kind), unique in sorted(groups.items()):
        rows = sorted(unique.values(), key=lambda r: (r[0], str(r[1]["article"])))
        amounts = [r[0] for r in rows]
        n = len(amounts)
        result.append(dict(currency=currency, condition=condition, match=kind,
            offer_count=n, minimum=str(min(amounts)), maximum=str(max(amounts)),
            average=str((sum(amounts) / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if n >= 3 else None,
            observed_at=max(r[1]["observed_at"] for r in rows),
            examples=[{k: e.get(k) for k in ("article", "amount", "currency", "url", "observed_at", "oem", "differences")} for _, e in rows[:10]]))
    return result
