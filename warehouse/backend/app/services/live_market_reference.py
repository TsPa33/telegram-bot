"""Opt-in exact-OEM market lookup. No client-supplied URLs or stock mutations.

Only explicitly approved server-side use of a fixed public OEM route is supported.
Cache contains public source cards, not tenant or user data. No background crawl.
"""
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import http.client
import ipaddress
import os
import re
import socket
import ssl
from threading import Lock
from time import monotonic

from app.services.aleto_adapter import Tree, price, source_url
from app.services.canonical_rules import surface, norm

HOST = "aleto.ua"
AGENT = "CarPot-PriceReference/1.0"
TTL = 86400
MAX_CACHE = 128
MAX_BYTES = 262144
MIN_INTERVAL = 3
_LOCK = Lock()
_CACHE = OrderedDict()
_ROBOTS = None
_LAST = float("-inf")


def enabled():
    # A deployment owner must first verify an agreement covering automated use
    # and anonymous display of the price data. Never infer that from HTTP 200.
    return (os.getenv("WAREHOUSE_MARKET_LIVE_ENABLED") == "true"
            and bool(os.getenv("WAREHOUSE_MARKET_ACCESS_APPROVAL", "").strip()))


def oem_key(value):
    value = (value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{3,39}", value) or not any(c.isdigit() for c in value):
        return None
    return value.replace("-", "")


def lookup_path(ctx):
    value = (ctx.get("oem") or "").strip()
    key = oem_key(value)
    if not key or not ctx.get("manufacturer") or not ctx.get("model"):
        return None
    # Known Toyota OEM route convention, verified for 81150-06C41.
    if norm(ctx["manufacturer"]) == "toyota" and len(key) == 10 and key[:5].isdigit():
        value = key[:5] + "-" + key[5:]
    return "/ua/n/" + value.lower() + "/"


class _PublicHTTPS(http.client.HTTPSConnection):
    def connect(self):
        # Resolve the fixed provider; reject private/reserved addresses and pin
        # the connection to the resolved IP. TLS still verifies the fixed host.
        records = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(r[4][0] for r in records))
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise OSError("non-public address")
        raw = socket.create_connection((addresses[0], 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=HOST)
        except BaseException:
            raw.close()
            raise


def fetch_text(path, limit=MAX_BYTES):
    if path != "/robots.txt" and not re.fullmatch(r"/ua/n/[a-z0-9][a-z0-9-]{3,39}/", path):
        raise ValueError("unapproved route")
    start = monotonic()
    conn = _PublicHTTPS(HOST, timeout=4, context=ssl.create_default_context())
    try:
        conn.request("GET", path, headers={"User-Agent": AGENT, "Accept-Encoding": "identity",
                                           "Accept": "text/plain" if path == "/robots.txt" else "text/html"})
        response = conn.getresponse()
        if response.status != 200 or response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise OSError("source response unavailable")
        expected = "text/plain" if path == "/robots.txt" else "text/html"
        if expected not in response.getheader("Content-Type", "").lower():
            raise OSError("unexpected content")
        length = response.getheader("Content-Length")
        if length and (not length.isdigit() or int(length) > limit):
            raise ValueError("response limit")
        chunks = bytearray()
        while True:
            remaining = 7 - (monotonic() - start)
            if remaining <= 0:
                raise TimeoutError("response deadline")
            if conn.sock:
                conn.sock.settimeout(min(4, remaining))
            chunk = response.read1(min(16384, limit + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > limit:
                raise ValueError("response limit")
        return chunks.decode("utf-8", errors="strict")
    finally:
        conn.close()


def robots_allows(text, path):
    # Accept only the currently observed simple, single wildcard-agent rule
    # format. Unexpected policy syntax fails closed rather than bypassing it.
    agent = False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            return False
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if value != "*" or agent:
                return False
            agent = True
        elif key in ("allow", "disallow"):
            if not agent or "*" in value or "$" in value or "%" in value:
                return False
            if key == "disallow" and value and path.startswith(value):
                return False
        elif key not in ("host", "sitemap"):
            return False
    return agent


def condition_for(labels):
    s = norm(labels)
    if "дефект" in s or "пошкодж" in s:
        return "damaged"
    if "нов" in s:
        return "new"
    if s in ("б в", "б у", "used"):
        return "used"
    if "відновлен" in s:
        return "refurbished"
    return "unknown"


def status_for(text):
    s = norm(text)
    if any(t in s for t in ("немає в наявності", "нет в наличии", "відсутній", "продано")):
        return "unavailable"
    if any(t in s for t in ("очікується", "ожидается", "під замовлення", "под заказ")):
        return "expected"
    if any(t in s for t in ("в наявності", "в наличии")):
        return "available"
    return "unknown"


def parse_cards(html, path, observed_at):
    if len(html.encode("utf-8")) > MAX_BYTES:
        raise ValueError("response limit")
    tree = Tree()
    tree.feed(html)
    tree.close()
    cards = [n for n in tree.root.all() if n.has("detail-item")]
    if not cards or len(cards) > 100:
        raise ValueError("unrecognized or excessive listing")
    rows = {}
    conflicts = set()
    for card in cards:
        # The live diagnostic identified these exact selectors. Raw source
        # identifiers remain internal; absent or contradictory evidence fails closed.
        title = card.find(cls="detail-item-title")
        chars = card.find(cls="detail-item-chars")
        labels = card.find(cls="detail-item-labels")
        if not title or not chars or not labels:
            continue
        link = title.find(tag="a", attr="href")
        if not link:
            continue
        fields = defaultdict(set)
        for n in chars.all():
            if n.tag != "small":
                continue
            b = n.find(tag="b")
            if b:
                label = n.text().casefold()
                if "арт" in label:
                    fields["article"].add(b.text())
                elif "ориг" in label or "oem" in label:
                    fields["oem"].add(b.text())
        if len(fields["article"]) != 1 or len(fields["oem"]) != 1:
            continue
        article, oem = next(iter(fields["article"])), next(iter(fields["oem"]))
        if not article or not oem_key(oem):
            continue
        try:
            url = source_url(link.attrs["href"], "https://" + HOST + path)
            uah, usd = card.find(cls="detail-item-uprice"), card.find(cls="detail-item-price")
            amounts = {c: price(node.text(), c.lower()) for c, node in (("UAH", uah), ("USD", usd)) if node}
        except (ValueError, TypeError):
            continue
        row = dict(article=article, oem=oem, title=title.text(), condition=condition_for(labels.text()),
                   availability=status_for(card.text()), amounts=amounts, url=url, observed_at=observed_at)
        if article in rows and rows[article] != row:
            conflicts.add(article)
        rows[article] = row
    if not rows:
        raise ValueError("no parseable evidence")
    return [r for a, r in rows.items() if a not in conflicts]


def references(ctx, rows):
    groups = defaultdict(list)
    own = surface(dict(title=ctx["name"], manufacturer=ctx["manufacturer"], model=ctx["model"]))
    own_tokens = own["phrase"].split()
    if not own_tokens or own["conflicts"]:
        return []
    for row in rows:
        if oem_key(row["oem"]) != oem_key(ctx["oem"]):
            continue
        title = norm(row["title"])
        if not all(re.search(r"(?<!\w)" + re.escape(norm(ctx[k])) + r"(?!\w)", title)
                   for k in ("manufacturer", "model")):
            continue
        other = surface(dict(title=row["title"], manufacturer=ctx["manufacturer"], model=ctx["model"]))
        tokens = other["phrase"].split()
        if not tokens or tokens[0] != own_tokens[0] or other["conflicts"]:
            continue
        if any(own[k] != "unknown" and own[k] != other[k] for k in ("side", "position")):
            continue
        if own["mount"] and own["mount"] != other["mount"]:
            continue
        features = other["features"]
        own_features = own["features"]
        comparison = ("assembly", "technology", "construction_type", "material", "ordinal_labels",
                      "option_labels", "engine_codes", "ratings", "connector_pins", "drive_labels",
                      "fuel_labels", "powertrain_labels")
        if any(own_features.get(k) and own_features[k] != features.get(k) for k in comparison):
            continue
        # Explicit source year ranges must not contradict the donor.
        year = ctx.get("year")
        mismatch = False
        for label in features.get("title_year_labels", []):
            dates = re.findall(r"\d+", label)
            if year and len(dates) == 2:
                bounds = [int(d) if len(d) == 4 else 2000 + int(d) for d in dates]
                if not bounds[0] <= year <= bounds[1]:
                    mismatch = True
            elif year and len(dates) == 1 and len(dates[0]) == 4 and int(dates[0]) != year:
                mismatch = True
        if mismatch or row["availability"] in ("unavailable", "expected"):
            continue
        # Separate unknown and positive availability, condition, installation,
        # assembly and the complete extracted technical signature. No fitment claim.
        signature = repr(sorted((k, v) for k, v in features.items()
                                if k not in ("title_models", "title_year_labels")))
        assembly = "complete" if "complete" in features.get("assembly", []) else (
            "bare" if "bare" in features.get("assembly", []) else "unknown")
        for currency, amount in row["amounts"].items():
            if amount is not None:
                key = (currency, row["condition"], row["availability"], assembly,
                       other["side"], other["position"], tuple(other["mount"]), signature)
                groups[key].append((Decimal(amount), row))
    result = []
    for key, values in sorted(groups.items(), key=lambda x: repr(x[0])):
        currency, condition, availability, assembly = key[:4]
        values.sort(key=lambda x: (x[0], x[1]["article"]))
        n = len(values)
        amounts = [v[0] for v in values]
        result.append(dict(currency=currency, condition=condition, availability=availability,
            assembly=assembly, match="similar", offer_count=n, minimum=str(min(amounts)),
            maximum=str(max(amounts)), average=str((sum(amounts)/n).quantize(Decimal("0.01"),
            rounding=ROUND_HALF_UP)) if n >= 3 else None,
            observed_at=max(r["observed_at"] for _, r in values),
            examples=[dict(amount=str(a), currency=currency, observed_at=r["observed_at"])
                      for a, r in values[:10]]))
    return result


def lookup(ctx):
    """Return (mode, groups, observed_at) or None. No network without approval."""
    global _ROBOTS, _LAST
    if not enabled():
        return None
    path = lookup_path(ctx)
    if not path or not _LOCK.acquire(blocking=False):
        return None
    try:
        now = monotonic()
        cached = _CACHE.get(path)
        if cached and now - cached[0] < TTL:
            _CACHE.move_to_end(path)
            rows, stamp = cached[1:]
            return "cached", references(ctx, rows), stamp
        if now - _LAST < MIN_INTERVAL:
            return None
        _LAST = now
        if not _ROBOTS or now - _ROBOTS[0] > 3600:
            _ROBOTS = (now, fetch_text("/robots.txt", 65536))
        if not robots_allows(_ROBOTS[1], path):
            return None
        stamp = datetime.now(timezone.utc).isoformat()
        rows = parse_cards(fetch_text(path), path, stamp)
        _CACHE[path] = (monotonic(), rows, stamp)
        _CACHE.move_to_end(path)
        while len(_CACHE) > MAX_CACHE:
            _CACHE.popitem(last=False)
        return "live", references(ctx, rows), stamp
    except (OSError, ValueError, TypeError, http.client.HTTPException):
        return None
    finally:
        _LAST = monotonic()
        _LOCK.release()
