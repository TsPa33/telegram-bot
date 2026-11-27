"""Bounded, individual-only public product reference. No search or crawl.

The public product JSON-LD is a single advertised observation, not a market mean.
Exact brand + number does not establish donor fitment or condition.
"""
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
import os
import re
from urllib.parse import urlsplit

HOST = "autopalma.parts"
MAX_BYTES = 786432
BRANDS = {
    "daf": "daf", "volvo": "volvo", "toyota": "toyota", "bmw": "bmw",
    "audi": "audi", "volkswagen": "volkswagen", "vw": "volkswagen",
    "skoda": "skoda", "ford": "ford", "renault": "renault",
    "hyundai": "hyundai", "kia": "kia", "mercedes benz": "mercedes-benz",
    "mercedes": "mercedes-benz", "opel": "opel", "peugeot": "peugeot",
    "citroen": "citroen", "nissan": "nissan", "honda": "honda",
    "mazda": "mazda", "mitsubishi": "mitsubishi", "man": "man",
    "scania": "scania", "iveco": "iveco",
}
CONDITIONS = {"NewCondition": "new", "UsedCondition": "used",
              "RefurbishedCondition": "refurbished", "DamagedCondition": "damaged"}


def enabled():
    return os.getenv("WAREHOUSE_MARKET_AUTOPALMA_ENABLED") == "true"


def brand_key(value):
    return BRANDS.get(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip())


def number_key(value):
    raw = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-]{3,39}", raw):
        return None
    key = re.sub(r"[\s-]", "", raw).lower()
    return key if 4 <= len(key) <= 40 and any(c.isdigit() for c in key) else None


def lookup_path(ctx):
    brand, number = brand_key(ctx.get("manufacturer")), number_key(ctx.get("oem"))
    return "/" + brand + "/" + number if brand and number else None


def valid_path(path):
    return bool(re.fullmatch(r"/[a-z0-9-]{2,30}/[a-z0-9]{4,40}", path)
                and path.split("/")[1] in set(BRANDS.values())
                and any(c.isdigit() for c in path.split("/")[2]))


def validated_url(value, expected_path=None):
    p = urlsplit(value)
    if (p.scheme != "https" or p.netloc != HOST or p.query or p.fragment
            or not valid_path(p.path) or (expected_path is not None and p.path != expected_path)):
        raise ValueError("invalid public product URL")
    return value


class _JsonLd(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.scripts = []
        self.parts = []
        self.size = 0

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.active = True
            self.parts = []
            self.size = 0

    def handle_data(self, data):
        if self.active:
            self.size += len(data)
            if self.size > 65536:
                raise ValueError("JSON-LD size")
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.active = False
            if len(self.scripts) >= 12:
                raise ValueError("too many JSON-LD scripts")
            self.scripts.append("".join(self.parts))


def _nodes(doc):
    if isinstance(doc, list):
        return doc[:100]
    if isinstance(doc, dict):
        graph = doc.get("@graph")
        return [doc] + (graph[:100] if isinstance(graph, list) else [])
    return []


def _schema_name(value):
    if not isinstance(value, str):
        return ""
    return value.rsplit("/", 1)[-1] if value.startswith(("https://schema.org/", "http://schema.org/")) else value


def parse_product(html, path, observed_at):
    """Return exactly one unambiguous offer; no guessed prices or analogs."""
    if not valid_path(path) or len(html.encode("utf-8")) > MAX_BYTES:
        raise ValueError("product bounds")
    parser = _JsonLd()
    parser.feed(html)
    parser.close()
    brand, number = path.strip("/").split("/")
    groups = []
    for script in parser.scripts:
        try:
            doc = json.loads(script, parse_float=Decimal)
        except (ValueError, RecursionError):
            continue
        for product in _nodes(doc):
            if not isinstance(product, dict) or product.get("@type") != "Product":
                continue
            b = product.get("brand")
            if not isinstance(b, dict) or brand_key(b.get("name")) != brand:
                continue
            if number_key(product.get("sku")) != number or not product.get("name"):
                continue
            try:
                url = validated_url(product.get("url", ""), path)
            except (ValueError, TypeError):
                continue
            offer = product.get("offers")
            # AggregateOffer/min-price and offer lists are intentionally not
            # counted as observations without an independently verified contract.
            if not isinstance(offer, dict) or offer.get("@type") != "Offer":
                continue
            if offer.get("url") != url:
                continue
            currency = offer.get("priceCurrency")
            if currency not in ("UAH", "USD"):
                continue
            raw = offer.get("price")
            if not isinstance(raw, (str, int, Decimal)) or isinstance(raw, bool):
                continue
            try:
                amount = Decimal(str(raw))
                if not amount.is_finite() or not Decimal("0") < amount <= Decimal("9999999999.99"):
                    continue
                if amount != amount.quantize(Decimal("0.01")):
                    continue
                amount = str(amount.quantize(Decimal("0.01")))
            except (InvalidOperation, ValueError):
                continue
            status = _schema_name(offer.get("availability"))
            if status not in ("", "InStock", "LimitedAvailability"):
                continue
            cond = CONDITIONS.get(_schema_name(offer.get("itemCondition")), "unknown")
            groups.append(dict(currency=currency, condition=cond,
                availability="available" if status else "unknown", assembly="unknown",
                match="similar", match_basis="brand_oem", source_name="AutoPalma",
                offer_count=1, minimum=amount, maximum=amount, average=None,
                observed_at=observed_at,
                examples=[dict(amount=amount, currency=currency, observed_at=observed_at, url=url)]))
    unique = []
    for group in groups:
        if group not in unique:
            unique.append(group)
    if len(unique) > 1:
        raise ValueError("conflicting product observations")
    return unique
