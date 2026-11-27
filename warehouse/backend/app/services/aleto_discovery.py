"""Find model catalogue candidates in the public Aleto category sitemap.

Accepts already-fetched XML. Source fetching and robots policy belong to the
caller. Matching here establishes a catalogue candidate, never OEM fitment.
"""
from dataclasses import dataclass
from io import BytesIO
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree

from app.services.aleto_adapter import source_url

MAX_SITEMAP_BYTES = 8 * 1024 * 1024
SITEMAP_NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
CATALOGUE_PATH = re.compile(r'/(?:ua/)?car/([a-z0-9-]+)/?')
PRODUCTION_YEARS = re.compile(
    r'(?:^|-)((?:19|20)\d{2})(?:-((?:19|20)\d{2}))?(-?)$'
)
SHORT_YEARS = re.compile(r'(?:^|-)(\d{2})-(?:(\d{2}))?$')


@dataclass(frozen=True)
class CatalogueCandidate:
    url: str
    year_from: int | None
    year_to: int | None


def slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def nearest_year(short_year: int, reference: int) -> int:
    return reference + (short_year - reference + 50) % 100 - 50


def catalogue_candidates(
    xml: bytes, manufacturer: str, model: str, *, year: int | None = None,
    generation: str = '',
) -> list[CatalogueCandidate]:
    if len(xml) > MAX_SITEMAP_BYTES:
        raise ValueError('SITEMAP_TOO_LARGE')
    # Require UTF-8 so declarations cannot be hidden in another encoding.
    decoded = xml.decode('utf-8-sig')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', decoded, re.IGNORECASE):
        raise ValueError('INVALID_SITEMAP')

    brand_key, model_key = slug(manufacturer), slug(model)
    if not brand_key or not model_key:
        return []
    vehicle_key = f'{brand_key}-{model_key}'
    generation_key = slug(generation)
    choices = {}
    try:
        nodes = ElementTree.iterparse(BytesIO(xml), events=('start', 'end'))
        _, root = next(nodes)
        if root.tag != SITEMAP_NS + 'urlset':
            raise ValueError('INVALID_SITEMAP')
        for event, node in nodes:
            if event != 'end' or node.tag != SITEMAP_NS + 'url':
                continue
            loc = node.findtext(SITEMAP_NS + 'loc')
            root.clear()
            if not loc:
                continue
            try:
                url = source_url(loc.strip())
            except ValueError:
                continue
            parsed = urlsplit(url)
            match = CATALOGUE_PATH.fullmatch(parsed.path)
            if not match or parsed.query:
                continue
            key = match[1]
            if key != vehicle_key and not key.startswith(vehicle_key + '-'):
                continue
            suffix = key[len(vehicle_key):]
            years = PRODUCTION_YEARS.search(suffix)
            first = int(years[1]) if years else None
            last = int(years[2]) if years and years[2] else first
            if years and years[3]:
                last = None
            if years is None:
                years = SHORT_YEARS.search(suffix)
                if years:
                    # Short dates appear in legacy catalogue URLs. With a target
                    # year, interpret them in its nearest century.
                    reference = year if year is not None else 2000
                    first = nearest_year(int(years[1]), reference)
                    last = nearest_year(int(years[2]), first) if years[2] else None
                    if last is not None and last < first:
                        first = last = None
            if year is not None and ((first and year < first) or (last and year > last)):
                continue
            variant = suffix[:years.start()] if years else suffix
            if generation_key and variant and f'-{generation_key}-' not in variant + '-':
                continue
            # Language variants describe the same catalogue.
            existing = choices.get(key)
            if existing is None or (parsed.path.startswith('/ua/') and '/ua/' not in existing.url):
                choices[key] = CatalogueCandidate(url, first, last)
    except ElementTree.ParseError:
        raise ValueError('INVALID_SITEMAP') from None
    return [choices[key] for key in sorted(choices)]
