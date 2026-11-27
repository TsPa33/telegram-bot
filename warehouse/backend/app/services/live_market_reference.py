"""Opt-in exact-OEM market lookup. No client-supplied URLs or stock mutations.

Only a user-initiated individual lookup of a fixed public OEM route is supported.
Cache contains public source cards, not tenant or user data. No background crawl.
"""
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import http.client
import ipaddress
import logging
import os
import re
import socket
import ssl
from threading import Lock
from time import monotonic, sleep
from urllib.parse import urlsplit

from app.services.aleto_adapter import Tree, price, source_url
from app.services.canonical_rules import surface, norm
from app.services import autopalma_market_reference as autopalma

HOST = "aleto.ua"
AGENT = "CarPot-PriceReference/1.0"
TTL = 86400
MAX_CACHE = 128
MAX_BYTES = 262144
_NEXT_REQUEST = {}
_SOURCE_BACKOFF = {}
_NAME_PAGES = OrderedDict()
NAME_MAX_BYTES = 786432
_LOCK = Lock()
_CACHE = OrderedDict()
_ROBOTS = None
_AUTOPALMA_ROBOTS = None
_AUTOPALMA_CACHE = OrderedDict()
_LOG = logging.getLogger("warehouse.market_reference")


class LookupFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def failed(code, phase):
    # No OEM, user ID, URL, raw HTML, exception text or credentials in logs.
    _LOG.warning("market_reference outcome=%s phase=%s", code, phase)
    return code, [], None


def enabled():
    # Limited staging pilot explicitly selected by the operator, not a claim
    # of provider authorization. Production remains off pending verified terms.
    return (os.getenv("WAREHOUSE_ENV") == "staging"
            and os.getenv("WAREHOUSE_MARKET_LIVE_ENABLED") == "true"
            and os.getenv("WAREHOUSE_MARKET_ACCESS_MODE") == "limited_individual")


def oem_key(value):
    value = re.sub(r"\s+", "", (value or "").strip().upper())
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{3,39}", value) or not any(c.isdigit() for c in value):
        return None
    return value.replace("-", "")


def lookup_path(ctx):
    value = re.sub(r"\s+", "", (ctx.get("oem") or "").strip())
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
        records = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(r[4][0] for r in records))
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise OSError("non-public address")
        raw = socket.create_connection((addresses[0], 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def fetch_text(path, limit=MAX_BYTES, *, host=HOST):
    if host not in (HOST, autopalma.HOST):
        raise ValueError("unapproved host")
    allowed = (bool(re.fullmatch(r"/ua/n/[a-z0-9][a-z0-9-]{3,39}/", path))
               if host == HOST else autopalma.valid_path(path))
    if host == HOST and catalog_path(path):
        allowed = True
    if path != "/robots.txt" and not allowed:
        raise ValueError("unapproved route")
    # Serial, short transport pacing rather than rejecting a user's next click.
    # Stop requests to a source that has actually rate-limited us.
    if monotonic() < _SOURCE_BACKOFF.get(host, 0):
        raise LookupFailure("source_access_denied")
    pause = _NEXT_REQUEST.get(host, 0) - monotonic()
    if pause > 0:
        sleep(pause)
    _NEXT_REQUEST[host] = monotonic() + 1
    start = monotonic()
    conn = _PublicHTTPS(host, timeout=4, context=ssl.create_default_context())
    try:
        conn.request("GET", path, headers={"User-Agent": AGENT, "Accept-Encoding": "identity",
                                           "Accept": "text/plain" if path == "/robots.txt" else "text/html"})
        response = conn.getresponse()
        if response.status == 404:
            raise LookupFailure("source_not_found")
        if response.status == 429:
            _SOURCE_BACKOFF[host] = monotonic() + 60
        if response.status in (401, 403, 429, 451):
            raise LookupFailure("source_access_denied")
        if 300 <= response.status < 400:
            raise LookupFailure("source_redirect")
        if response.status != 200:
            raise LookupFailure("source_http_error")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise LookupFailure("source_content_error")
        expected = "text/plain" if path == "/robots.txt" else "text/html"
        if expected not in response.getheader("Content-Type", "").lower():
            raise LookupFailure("source_content_error")
        length = response.getheader("Content-Length")
        if length and (not length.isdigit() or int(length) > limit):
            raise LookupFailure("source_response_limit")
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
            if not agent or "*" in value or "%" in value or "$" in value[:-1]:
                return False
            matched = (path == value[:-1]) if value.endswith("$") else path.startswith(value)
            if key == "disallow" and value and matched:
                return False
        elif key not in ("host", "sitemap"):
            return False
    return agent


def condition_for(labels):
    s = norm(labels)
    if "дефект" in s or "пошкодж" in s:
        return "damaged"
    if "відновлен" in s or "восстановлен" in s:
        return "refurbished"
    if "нов" in s:
        return "new"
    if s in ("б в", "б у", "used"):
        return "used"
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


def parse_cards(html, path, observed_at, *, by_name=False):
    if len(html.encode("utf-8")) > (NAME_MAX_BYTES if by_name else MAX_BYTES):
        raise ValueError("response limit")
    tree = Tree()
    tree.feed(html)
    tree.close()
    cards = [n for n in tree.root.all() if n.has("detail-item")]
    if len(cards) > 100:
        raise LookupFailure("source_response_limit")
    if not cards:
        raise LookupFailure("source_no_cards")
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
        if len(fields["article"]) != 1 or len(fields["oem"]) > 1 or (not by_name and len(fields["oem"]) != 1):
            continue
        article, oem = next(iter(fields["article"])), next(iter(fields["oem"]), "")
        if not article or (not by_name and not oem_key(oem)):
            continue
        try:
            url = source_url(link.attrs["href"], "https://" + HOST + path)
            uah, usd = card.find(cls="detail-item-uprice"), card.find(cls="detail-item-price")
        except (ValueError, TypeError):
            continue
        amounts = {}
        for c, node in (("UAH", uah), ("USD", usd)):
            if node:
                try:
                    amounts[c] = price(node.text(), c.lower())
                except (ValueError, TypeError):
                    continue
        if not any(amounts.values()):
            continue
        row = dict(article=article, oem=oem, title=link.text(), condition=condition_for(labels.text()),
                   availability=status_for(card.text()), amounts=amounts, url=url, observed_at=observed_at)
        if article in rows and rows[article] != row:
            conflicts.add(article)
        rows[article] = row
    if not rows:
        raise LookupFailure("source_parse_error")
    return [r for a, r in rows.items() if a not in conflicts]


def references(ctx, rows, *, by_name=False):
    groups = defaultdict(list)
    own = surface(dict(title=ctx["name"], manufacturer=ctx["manufacturer"], model=ctx["model"]))
    own_tokens = own["phrase"].split()
    if not own_tokens or own["conflicts"]:
        return []
    for row in rows:
        if not by_name and oem_key(row["oem"]) != oem_key(ctx["oem"]):
            continue
        title = norm(row["title"])
        if not all(re.search(r"(?<!\w)" + re.escape(norm(ctx[k])) + r"(?!\w)", title)
                   for k in ("manufacturer", "model")):
            continue
        other = surface(dict(title=row["title"], manufacturer=ctx["manufacturer"], model=ctx["model"]))
        tokens = other["phrase"].split()
        if not tokens or other["conflicts"]:
            continue
        if by_name:
            if not name_match(ctx["name"], row["title"], ctx):
                continue
        elif tokens[:len(own_tokens[:2])] != own_tokens[:2]:
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
            examples=[dict(amount=str(a), currency=currency, observed_at=r["observed_at"], url=r["url"])
                      for a, r in values[:10]]))
    if by_name:
        for g in result:
            g.update(match_basis="name_model", source_name="Aleto")
    return result


def _fallback(ctx, original, now):
    """Try at most one independent public product path per explicit lookup.

    An access denial, rate limit, or robots error is never a fallback trigger.
    The caller owns the shared lock and the same per-click budget.
    """
    global _AUTOPALMA_ROBOTS
    if not autopalma.enabled():
        return original
    path = autopalma.lookup_path(ctx)
    if not path:
        return original
    phase = "robots"
    try:
        if not _AUTOPALMA_ROBOTS or now - _AUTOPALMA_ROBOTS[0] > 3600:
            _AUTOPALMA_ROBOTS = (now, fetch_text("/robots.txt", 65536, host=autopalma.HOST))
        if not robots_allows(_AUTOPALMA_ROBOTS[1], path):
            return failed("robots_denied", "autopalma_robots")
        phase = "product"
        html = fetch_text(path, autopalma.MAX_BYTES, host=autopalma.HOST)
        stamp = datetime.now(timezone.utc).isoformat()
        phase = "parse"
        groups = autopalma.parse_product(html, path, stamp)
        if not groups:
            return failed("no_comparable", "autopalma_parse")
        _AUTOPALMA_CACHE[path] = (monotonic(), groups, stamp)
        _AUTOPALMA_CACHE.move_to_end(path)
        while len(_AUTOPALMA_CACHE) > MAX_CACHE:
            _AUTOPALMA_CACHE.popitem(last=False)
        _LOG.warning("market_reference outcome=matched phase=autopalma groups=%d", len(groups))
        return "live", groups, stamp
    except LookupFailure as exc:
        return failed("robots_unavailable" if phase == "robots" else exc.code, "autopalma_" + phase)
    except (TimeoutError, socket.timeout):
        return failed("source_timeout", "autopalma_" + phase)
    except (OSError, http.client.HTTPException):
        return failed("source_network_error", "autopalma_" + phase)
    except (ValueError, TypeError, RecursionError):
        return failed("source_parse_error" if phase == "parse" else "source_content_error", "autopalma_" + phase)


def _lookup_oem(ctx):
    """OEM lookup remains an optional precision/fallback route."""
    global _ROBOTS
    path = lookup_path(ctx)
    if not path:
        return failed("missing_oem", "input")
    phase = "cache"
    try:
        now = monotonic()
        cached = _CACHE.get(path)
        prior = None
        if cached and now - cached[0] < TTL:
            _CACHE.move_to_end(path)
            rows, stamp = cached[1:]
            groups = references(ctx, rows)
            prior = ("cached", groups, stamp)
            if groups or not autopalma.enabled():
                return prior
        other_path = autopalma.lookup_path(ctx) if autopalma.enabled() else None
        other = _AUTOPALMA_CACHE.get(other_path) if other_path else None
        if other and now - other[0] < TTL:
            _AUTOPALMA_CACHE.move_to_end(other_path)
            return "cached", other[1], other[2]
        if prior and not other_path:
            return prior
        if prior:
            return _fallback(ctx, prior, now)
        phase = "robots"
        if not _ROBOTS or now - _ROBOTS[0] > 3600:
            _ROBOTS = (now, fetch_text("/robots.txt", 65536))
        if not robots_allows(_ROBOTS[1], path):
            return failed("robots_denied", phase)
        phase = "product"
        stamp = datetime.now(timezone.utc).isoformat()
        html = fetch_text(path)
        phase = "parse"
        rows = parse_cards(html, path, stamp)
        _CACHE[path] = (monotonic(), rows, stamp)
        _CACHE.move_to_end(path)
        while len(_CACHE) > MAX_CACHE:
            _CACHE.popitem(last=False)
        phase = "matching"
        groups = references(ctx, rows)
        _LOG.warning("market_reference outcome=%s phase=%s cards=%d groups=%d",
                     "matched" if groups else "no_comparable", phase, len(rows), len(groups))
        result = ("live", groups, stamp)
        return result if groups else _fallback(ctx, result, now)
    except LookupFailure as exc:
        result = failed("robots_unavailable" if phase == "robots" else exc.code, phase)
        if phase in ("product", "parse") and exc.code in ("source_not_found", "source_no_cards"):
            return _fallback(ctx, result, monotonic())
        return result
    except (TimeoutError, socket.timeout):
        return failed("source_timeout", phase)
    except (OSError, http.client.HTTPException):
        return failed("source_network_error", phase)
    except (ValueError, TypeError):
        return failed("source_parse_error" if phase in ("parse", "matching") else "source_content_error", phase)



# Only real navigation links from public manufacturer/model catalogues are
# followed. No internal search endpoint, pagination sweep or invented product URLs.
_BRAND_SLUGS = {"mercedes benz": "mercedes-benz", "vw": "volkswagen",
                "alfa romeo": "alfa-romeo"}
# Confirmed public model path, also present in the existing Aleto adapter.
_KNOWN_MODELS = {("volvo", "xc90"): ("/ua/car/volvo-xc90-16-/", 2016, 2026),
                 ("volvo", "xc60"): ("/ua/car/volvo-xc60-2018-2023/", 2018, 2023)}
_WORDS = {
    "дзеркал": "mirror", "зеркал": "mirror", "mirror": "mirror",
    "бічн": "side", "боков": "side", "ресор": "spring", "рессор": "spring",
    "пружин": "spring", "кронштейн": "bracket", "опор": "bracket",
    "пробк": "plug", "заглушк": "plug", "маслян": "oil", "масля": "oil",
    "олив": "oil", "піддон": "pan", "поддон": "pan",
    "фільтр": "filter", "фильтр": "filter", "повітр": "air", "воздуш": "air",
    "фар": "headlight", "бампер": "bumper", "двер": "door",
    "датчик": "sensor", "насос": "pump", "помп": "pump",
    "капот": "hood", "радіатор": "radiator", "радиатор": "radiator",
}
_STOP = {"в", "у", "на", "для", "з", "из", "і", "и", "та", "комплект", "шт"}


def catalog_path(path):
    return bool(re.fullmatch(r"/ua/mark/[a-z0-9][a-z0-9-]{0,59}/", path)
                or re.fullmatch(r"/ua/car/[a-z0-9][a-z0-9-]{0,99}/(?:[a-z0-9][a-z0-9-]{0,99}/)?", path))


def _model_key(value):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)", "", str(value or "").lower()))


def _brand(ctx):
    maker = norm(ctx.get("manufacturer") or "")
    slug = _BRAND_SLUGS.get(maker, maker.replace(" ", "-"))
    return slug if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", slug) else None


def _name_tokens(value, ctx):
    parsed = surface(dict(title=value, manufacturer=ctx.get("manufacturer") or "",
                          model=ctx.get("model") or ""))
    words = set()
    for token in parsed["phrase"].split():
        if token in _STOP or len(token) < 3 or token.isdigit():
            continue
        mapped = next((v for prefix,v in _WORDS.items() if token.startswith(prefix)), None)
        words.add(mapped or token)
    return words


def name_match(name, title, ctx):
    wanted = _name_tokens(name, ctx)
    actual = _name_tokens(title, ctx)
    if not wanted or not actual:
        return False
    # A generic word alone is insufficient for a multiword component.
    overlap = wanted & actual
    return bool(overlap) and (wanted <= actual or
        (len(wanted) >= 3 and len(overlap) >= 2 and len(overlap)/len(wanted) >= 0.75))


def _navigation(html, parent):
    tree = Tree()
    tree.feed(html)
    tree.close()
    links = {}
    for a in tree.root.all():
        if a.tag != "a" or not a.attrs.get("href"):
            continue
        try:
            url = source_url(a.attrs["href"], "https://" + HOST + parent)
            u = urlsplit(url)
            if u.query or u.fragment or not catalog_path(u.path):
                continue
            title = a.text()
            if title and len(title) <= 250:
                links.setdefault(u.path, title)
        except (ValueError, TypeError):
            continue
    return links


def _catalog_html(path):
    global _ROBOTS
    now = monotonic()
    if not _ROBOTS or now - _ROBOTS[0] > 3600:
        _ROBOTS = (now, fetch_text("/robots.txt", 65536))
    if not robots_allows(_ROBOTS[1], path):
        raise LookupFailure("robots_denied")
    cached = _NAME_PAGES.get(path)
    if cached and now - cached[0] < TTL:
        _NAME_PAGES.move_to_end(path)
        return cached[1], cached[2], False
    html = fetch_text(path, NAME_MAX_BYTES)
    stamp = datetime.now(timezone.utc).isoformat()
    _NAME_PAGES[path] = (monotonic(), html, stamp)
    _NAME_PAGES.move_to_end(path)
    while len(_NAME_PAGES) > 24:
        _NAME_PAGES.popitem(last=False)
    return html, stamp, True


def _model_path(ctx):
    brand, model = _brand(ctx), _model_key(ctx.get("model"))
    if not brand or not model:
        return None
    # Generation suffix is accepted for the known XC90 II/XC60 II paths only
    # when the donor year also agrees.
    known = _KNOWN_MODELS.get((brand, model))
    if not known and model.endswith("ii"):
        known = _KNOWN_MODELS.get((brand, model[:-2]))
    year = ctx.get("year")
    if known and isinstance(year, int) and known[1] <= year <= known[2]:
        return known[0]
    root = "/ua/mark/" + brand + "/"
    html, _, _ = _catalog_html(root)
    candidates = []
    for path, title in _navigation(html, root).items():
        if not re.fullmatch(r"/ua/car/[a-z0-9][a-z0-9-]{0,99}/", path):
            continue
        slug = path.split("/")[3]
        if not slug.startswith(brand + "-"):
            continue
        # Require the exact model prefix with a boundary, not XC90 vs XC90II
        # or XF vs XF105 by substring. Check explicit full-year ranges.
        parts = re.split(r"[- ]+", slug[len(brand)+1:])
        prefix = ""
        matched = False
        for i, token in enumerate(parts):
            prefix += token
            if prefix == model:
                matched = True
                break
            if not model.startswith(prefix):
                break
        if not matched:
            continue
        dates = [int(x) for x in re.findall(r"\b(?:19|20)\d{2}\b", title)]
        if year and len(dates) >= 2 and not min(dates) <= year <= max(dates):
            continue
        if year and len(dates) == 1 and dates[0] != year:
            continue
        candidates.append(path)
    return candidates[0] if len(set(candidates)) == 1 else None


def _lookup_name(ctx):
    if not ctx.get("name") or not ctx.get("manufacturer") or not ctx.get("model"):
        return failed("missing_vehicle", "name")
    try:
        model_path = _model_path(ctx)
        if not model_path:
            return failed("no_comparable", "name_model")
        html, stamp, fresh = _catalog_html(model_path)
        # Exact model labels for the comparison, stripped of source generation
        # notation only for confirmed known model/year combinations.
        compare = dict(ctx)
        if _model_key(compare["model"]) in ("xc90ii", "xc60ii"):
            compare["model"] = _model_key(compare["model"])[:-2]
        def result_from(page, path, stamp):
            try:
                rows = parse_cards(page, path, stamp, by_name=True)
            except LookupFailure as exc:
                if exc.code in ("source_no_cards", "source_parse_error"):
                    return []
                raise
            return references(compare, rows, by_name=True)
        groups = result_from(html, model_path, stamp)
        if not groups:
            links = _navigation(html, model_path)
            # The live catalogue root exposes broad sections, not all leaves.
            # These XC90 mirror routes were observed on the public category
            # page on 2026-11-27; robots are checked even for known links.
            wanted = _name_tokens(ctx["name"], compare)
            own = surface(dict(title=ctx["name"], manufacturer=compare["manufacturer"], model=compare["model"]))
            if model_path == "/ua/car/volvo-xc90-16-/" and wanted and wanted <= {"mirror","side"}:
                side = own["side"]
                leaf = {"left":"3-zerkalo-bokovoe-levoe/","right":"3-zerkalo-bokovoe-pravoe/"}.get(side,"bokovoe-zerkalo/")
                links.setdefault(model_path + leaf, ctx["name"])
            # Only one best matching category from the selected model's actual
            # links. Never enumerate all categories or search pages.
            scored = []
            wanted = _name_tokens(ctx["name"], compare)
            for path,title in links.items():
                if not path.startswith(model_path) or path == model_path:
                    continue
                if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}/", path[len(model_path):]):
                    continue
                actual = _name_tokens(title, compare)
                shared = wanted & actual
                if shared and wanted and (wanted <= actual or actual <= wanted):
                    # Match the installation side when a category specifies it.
                    direction = surface(dict(title=title))["side"]
                    if own["side"] != "unknown" and direction not in ("unknown",own["side"]):
                        continue
                    scored.append((len(shared), -len(actual ^ wanted), path))
            if scored:
                scored.sort(reverse=True)
                best = scored[0]
                if len(scored) == 1 or best[:2] > scored[1][:2]:
                    page, stamp, fresh = _catalog_html(best[2])
                    groups = result_from(page, best[2], stamp)
        if groups:
            _LOG.warning("market_reference outcome=matched phase=name groups=%d", len(groups))
            return ("live" if fresh else "cached"), groups, stamp
        return failed("no_comparable", "name")
    except LookupFailure as exc:
        return failed(exc.code, "name")
    except (TimeoutError, socket.timeout):
        return failed("source_timeout", "name")
    except (OSError, http.client.HTTPException):
        return failed("source_network_error", "name")
    except (ValueError, TypeError, RecursionError):
        return failed("source_parse_error", "name")


def lookup(ctx):
    """Individual lookup: name/model first, optional OEM and second source."""
    if not enabled():
        return failed("disabled", "policy")
    if not _LOCK.acquire(timeout=3):
        return failed("busy", "concurrency")
    try:
        # Context is assembled by the authenticated server, never client URLs.
        if ctx.get("allow_name_search"):
            result = _lookup_name(ctx)
            if result[1] or not lookup_path(ctx):
                return result
            if result[0] in ("robots_denied", "robots_unavailable", "source_access_denied", "source_redirect"):
                return result
        return _lookup_oem(ctx)
    finally:
        _LOCK.release()
