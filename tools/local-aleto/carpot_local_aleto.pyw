# -*- coding: utf-8 -*-
"""CarPot Local Aleto — local Windows GUI and safe staging CSV handoff.

Uses only Python standard library. Scrapes only the selected public Aleto
catalogue, respects robots.txt and crawl delays, and never bypasses HTTP 403.
No credentials are collected or stored. Catalogue upload remains the existing
browser-authenticated, preview-first staging workflow.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from contextlib import closing
from html.parser import HTMLParser
from io import BytesIO
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import sqlite3
import threading
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, unquote
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree
import webbrowser

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import local_store
from catalogue_client import CatalogueClient
from catalogue_dialog import CatalogueDialog
from clipboard_support import install_clipboard_support

JOB_STATUS = {
    'queued': 'Очікує продовження', 'paused': 'Призупинено', 'failed': 'Помилка збору',
    'partial': 'Потрібна перевірка', 'completed': 'Збір завершено', 'limited': 'Досягнуто ліміту',
    'cancelled': 'Скасовано',
}

APP_NAME = 'CarPot Local Aleto'
VERSION = '1.1.2'
CARPOT_URL = 'https://confident-sparkle-warehouse-staging.up.railway.app/administration/catalogue/import'
SEED_DB = Path(__file__).resolve().parent / 'migration' / 'local_aleto.sqlite3'
DATA_DIR = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'CarPot' / (
    'LocalAleto-v1.1' if SEED_DB.is_file() else 'LocalAleto'
)
DB_PATH = DATA_DIR / 'local_aleto.sqlite3'
USER_AGENT = 'CarPotCatalogueWorker/1.0'
MIN_INTERVAL_SECONDS = 3
MAX_BYTES_PAGE = 512 * 1024
MAX_BYTES_ROBOTS = 128 * 1024
MAX_BYTES_SITEMAP = 8 * 1024 * 1024
MAX_PAGES = 1000
MAX_RECORDS = 50000
MAX_CSV_BYTES = 8 * 1024 * 1024  # Warehouse has a separate 16-MiB hard limit
MAX_CSV_ROWS = 2000
REQUEST_TIMEOUT = 20
SITEMAPS = (
    'https://aleto.ua/sitemap-categories.xml',
    'https://aleto.ua/sitemap-categories-new.xml',
)
CSV_COLUMNS = (
    'schema_version', 'source', 'source_article', 'manufacturer', 'model',
    'generation', 'year_from', 'year_to', 'category', 'subcategory',
    'part_name', 'oem', 'condition', 'side', 'position', 'price_uah',
    'price_usd', 'source_url', 'observed_at', 'source_record',
)
PROHIBITED_PATH = {'personal', 'register', 'cart', 'search', 'search-adv'}
DARK = '#101821'
PANEL = '#192532'
FIELD = '#243341'
TEXT = '#F2F5F7'
MUTED = '#A7B5C1'
ACCENT = '#00B5A4'
SITEMAP_NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
PRODUCTION_YEARS = re.compile(r'(?:^|-)((?:19|20)\d{2})(?:-((?:19|20)\d{2}))?(-?)$')
SHORT_YEARS = re.compile(r'(?:^|-)(\d{2})-(?:(\d{2}))?$')


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def source_url(url, base=None):
    if not isinstance(url, str) or not url or len(url) > 2000 or '\\' in url or any(ord(c) < 33 for c in url):
        raise ValueError('Некоректна адреса джерела')
    resolved = urljoin(base, url) if base else url
    parsed = urlsplit(resolved)
    if (parsed.scheme != 'https' or parsed.hostname not in ('aleto.ua', 'www.aleto.ua')
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment):
        raise ValueError('Дозволено лише публічні HTTPS-сторінки aleto.ua')
    parts = unquote(parsed.path).lower().split('/')
    if any(x in ('.', '..') or x in PROHIBITED_PATH for x in parts):
        raise ValueError('Ця частина сайту недоступна для збору')
    return resolved


def catalogue_url(url):
    result = source_url(url)
    if not re.fullmatch(r'/(?:ua/)?car/[a-z0-9-]+/', urlsplit(result).path, re.I):
        raise ValueError('Вкажіть посилання на каталог автомобіля /car/.../')
    return result


def within_catalogue(target, root):
    """Keep only selected model URLs, allowing Aleto's RU/UA locale switch."""
    a, b = urlsplit(target), urlsplit(root)
    if a.hostname != b.hostname or a.scheme != b.scheme or a.scheme != 'https':
        return False

    def catalogue_model(path):
        pieces = path.strip('/').split('/')
        if pieces and pieces[0] == 'ua':
            pieces = pieces[1:]
        if len(pieces) < 2 or pieces[0] != 'car':
            return None
        return pieces[1].lower()

    return bool(catalogue_model(b.path)
                and catalogue_model(a.path) == catalogue_model(b.path))



def _make_slug(value):
    # Account for Cyrillic brand names entered by accident: user can also paste
    # the exact catalogue URL, which remains the most reliable selection.
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def _nearest_year(short, year):
    return year + (short - year + 50) % 100 - 50


def find_candidates(xml, manufacturer, model, year=None, generation=''):
    if len(xml) > MAX_BYTES_SITEMAP:
        raise ValueError('Завеликий sitemap')
    decoded = xml.decode('utf-8-sig')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', decoded, re.I):
        raise ValueError('Некоректний sitemap')
    brand_key = _make_slug(manufacturer)
    model_key = _make_slug(model)
    # VIN decoders may already include the make in the model (e.g. 'Polestar 2').
    # Avoid 'polestar-polestar-2', which hides valid Aleto catalogue links.
    key_prefix = model_key if model_key == brand_key or model_key.startswith(brand_key + '-') else brand_key + '-' + model_key
    gen_key = _make_slug(generation)
    found = {}
    source = ElementTree.iterparse(BytesIO(xml), events=('start', 'end'))
    _, root = next(source)
    if root.tag != SITEMAP_NS + 'urlset':
        raise ValueError('Некоректний формат sitemap')
    for event, item in source:
        if event != 'end' or item.tag != SITEMAP_NS + 'url':
            continue
        raw = item.findtext(SITEMAP_NS + 'loc')
        root.clear()
        if not raw:
            continue
        try:
            url = source_url(raw.strip())
        except ValueError:
            continue
        parsed = urlsplit(url)
        match = re.fullmatch(r'/(?:ua/)?car/([a-z0-9-]+)/?', parsed.path)
        if not match or parsed.query:
            continue
        slug = match.group(1)
        if slug != key_prefix and not slug.startswith(key_prefix + '-'):
            continue
        suffix = slug[len(key_prefix):]
        y = PRODUCTION_YEARS.search(suffix)
        first = int(y.group(1)) if y else None
        last = int(y.group(2)) if y and y.group(2) else first
        if y and y.group(3):
            last = None
        if not y:
            y = SHORT_YEARS.search(suffix)
            if y:
                first = _nearest_year(int(y.group(1)), year or 2000)
                last = _nearest_year(int(y.group(2)), first) if y.group(2) else None
                if last is not None and last < first:
                    first = last = None
        if year and ((first and year < first) or (last and year > last)):
            continue
        variant = suffix[:y.start()] if y else suffix
        if gen_key and variant and f'-{gen_key}-' not in variant + '-':
            continue
        existing = found.get(slug)
        if not existing or parsed.path.startswith('/ua/') and '/ua/' not in existing:
            found[slug] = url
    return [found[k] for k in sorted(found)]


def find_brand_page_candidates(html, page_url, manufacturer, model, year=None, generation=''):
    """Find catalogues linked on Aleto's public manufacturer page.

    The sitemap can omit recently added catalogues. Reuse the same URL and
    model/year checks rather than trusting arbitrary manufacturer-page links.
    """
    if len(html) > 2 * 1024 * 1024:
        raise ValueError('Завелика сторінка марки')
    links = set()

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag != 'a' or len(links) >= 10000:
                return
            href = dict(attrs).get('href')
            if not href:
                return
            try:
                url = source_url(href, page_url)
            except ValueError:
                return
            if re.fullmatch(r'/(?:ua/)?car/[a-z0-9-]+/?', urlsplit(url).path):
                links.add(url)

    links_parser = Links(convert_charrefs=True)
    links_parser.feed(html.decode('utf-8-sig'))
    links_parser.close()
    root = ElementTree.Element(SITEMAP_NS + 'urlset')
    for url in sorted(links):
        item = ElementTree.SubElement(root, SITEMAP_NS + 'url')
        ElementTree.SubElement(item, SITEMAP_NS + 'loc').text = url
    return find_candidates(ElementTree.tostring(root, encoding='utf-8'),
                           manufacturer, model, year, generation)


class SourceError(Exception):
    pass


class SourceClient:
    def __init__(self, stop_event=None):
        self.stop = stop_event or threading.Event()
        self.next_at = 0.0
        self.policies = {}

    def _sleep(self):
        while time.monotonic() < self.next_at:
            if self.stop.wait(min(0.2, max(0.0, self.next_at - time.monotonic()))):
                raise InterruptedError('Збір призупинено')
        if self.stop.is_set():
            raise InterruptedError('Збір призупинено')

    def _curl_get(self, url, max_size, types):
        """On Windows reuse the curl.exe HTTP/1.1 client that was verified locally."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix='response-', suffix='.tmp',
                                         dir=DATA_DIR, delete=False) as temporary:
            path = Path(temporary.name)
        try:
            args = [shutil.which('curl.exe'), '--http1.1', '--location',
                    '--proto', '=https', '--proto-redir', '=https',
                    '--max-redirs', '3', '--silent', '--show-error',
                    '--max-time', str(REQUEST_TIMEOUT), '--connect-timeout', '10',
                    '--max-filesize', str(max_size),
                    '-A', USER_AGENT,
                    '-H', 'Accept-Encoding: identity',
                    '-H', 'Accept: text/html,application/xml,text/xml,text/plain;q=0.8',
                    '--output', str(path), '--write-out',
                    '%{http_code}\n%{content_type}\n%{url_effective}', url]
            result = subprocess.run(args, capture_output=True, check=False,
                                    creationflags=0x08000000 if os.name == 'nt' else 0,
                                    timeout=REQUEST_TIMEOUT + 5)
            metadata = result.stdout.decode('utf-8', 'replace').splitlines()
            if len(metadata) < 3:
                raise SourceError('curl.exe: ' + result.stderr.decode('utf-8', 'replace')[:180])
            status, kind, effective = metadata[-3:]
            source_url(effective)
            if status != '200':
                raise SourceError('SOURCE_HTTP_' + status)
            if result.returncode:
                raise SourceError('curl.exe: ' + result.stderr.decode('utf-8', 'replace')[:180])
            content_type = kind.split(';')[0].strip().lower()
            if content_type not in types:
                raise SourceError('Неочікуваний тип відповіді: ' + content_type)
            if path.stat().st_size > max_size:
                raise SourceError('Сторінка перевищує ліміт розміру')
            return path.read_bytes()
        except subprocess.TimeoutExpired:
            raise SourceError('Перевищено час очікування curl.exe') from None
        finally:
            path.unlink(missing_ok=True)

    def _get(self, url, max_size, types):
        self._sleep()
        try:
            if os.name == 'nt' and shutil.which('curl.exe'):
                return self._curl_get(url, max_size, types)
            request = Request(url, headers={
                'User-Agent': USER_AGENT,
                'Accept-Encoding': 'identity',
                'Accept': 'text/html,application/xml,text/xml,text/plain;q=0.8',
            })
            with urlopen(request, timeout=REQUEST_TIMEOUT) as reply:
                source_url(reply.geturl())  # Reject redirects off the approved source.
                content_type = reply.headers.get_content_type()
                if content_type not in types:
                    raise SourceError('Неочікуваний тип відповіді: ' + content_type)
                if reply.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    raise SourceError('Непідтримуване стиснення відповіді')
                data = reply.read(max_size + 1)
                if len(data) > max_size:
                    raise SourceError('Розмір сторінки перевищує ліміт')
                return data
        except HTTPError as exc:
            raise SourceError(f'SOURCE_HTTP_{exc.code}') from None
        except URLError as exc:
            raise SourceError('Помилка мережі: ' + str(exc.reason)[:120]) from None
        except TimeoutError:
            raise SourceError('Перевищено час очікування відповіді') from None
        finally:
            self.next_at = time.monotonic() + MIN_INTERVAL_SECONDS

    def read(self, url, max_size, types):
        url = source_url(url)
        host = urlsplit(url).hostname
        if host not in self.policies:
            robots = f'https://{host}/robots.txt'
            text = self._get(robots, MAX_BYTES_ROBOTS, ('text/plain',)).decode('utf-8-sig')
            if not any(x.lower().startswith('user-agent:') for x in text.splitlines()):
                raise SourceError('Не вдалося перевірити robots.txt')
            policy = RobotFileParser()
            policy.parse(text.splitlines())
            self.policies[host] = policy
        policy = self.policies[host]
        if not policy.can_fetch(USER_AGENT, url):
            raise SourceError('ROBOTS_DISALLOWED: збір цієї сторінки заборонено')
        delay = policy.crawl_delay(USER_AGENT) or 0
        rate = policy.request_rate(USER_AGENT)
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        self.next_at = max(self.next_at, time.monotonic() + max(0, delay - MIN_INTERVAL_SECONDS))
        return self._get(url, max_size, types)


class Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        return clean(' '.join(x.text() if isinstance(x, Node) else x for x in self.children))

    def all(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.all()

    def has(self, cls):
        return cls in self.attrs.get('class', '').split()

    def find(self, cls=None, tag=None, attr=None):
        return next((x for x in self.all() if (not cls or x.has(cls))
                     and (not tag or x.tag == tag)
                     and (not attr or attr in x.attrs)), None)


class HTMLTree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
        self.nodes = 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 25000 or len(self.stack) > 90:
            raise SourceError('Сторінка HTML занадто складна')
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
                       'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def price_text(value, currency):
    suffix = {'uah': r'(?:грн\.?|₴|UAH)', 'usd': r'(?:\$|USD)'}[currency]
    text = clean(value)
    if not text:
        return ''
    match = re.fullmatch(r'(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*' + suffix, text, re.I)
    if not match:
        raise ValueError('Некоректний формат ціни')
    from decimal import Decimal
    amount = Decimal(re.sub(r'[ \u00a0\u202f]', '', match.group(1)).replace(',', '.'))
    if not amount.is_finite() or amount <= 0 or amount > Decimal('9999999999.99'):
        raise ValueError('Некоректне значення ціни')
    return str(amount.quantize(Decimal('0.01')))


def decode_html_page(raw):
    """Decode Aleto HTML safely without discarding the entire crawl on one bad byte.

    Pages may use UTF-8 or explicitly declare Windows-1251. If UTF-8 contains
    isolated invalid bytes, retain correctly decoded content but report a
    data-quality warning so the crawl finishes as partial, not 'completed'.
    """
    if not isinstance(raw, bytes):
        raise TypeError('HTML має бути байтовим вмістом')
    head = raw[:8192]
    declared = re.search(
        rb'<meta\b[^>]{0,500}?\bcharset\s*=\s*["\']?\s*([a-zA-Z0-9_-]+)',
        head, re.I,
    )
    charset = declared.group(1).decode('ascii').lower().replace('_', '-') if declared else ''
    if charset in ('windows-1251', 'cp1251', 'win-1251'):
        return raw.decode('cp1251'), 0
    if charset not in ('', 'utf-8', 'utf8'):
        raise SourceError('Непідтримуване кодування HTML: ' + charset[:32])
    try:
        return raw.decode('utf-8-sig'), 0
    except UnicodeDecodeError:
        # A single invalid byte must not lose previously collected pages or
        # falsely turn the entire source into Windows-1251 mojibake.
        repaired = raw.decode('utf-8-sig', errors='replace')
        bad = repaired.count('\ufffd')
        if bad > max(50, len(raw) // 500):
            raise SourceError('HTML_ENCODING_MISMATCH: сторінка має забагато пошкоджених символів')
        return repaired, bad


def extract_page(html, url):
    tree = HTMLTree()
    tree.feed(html)
    tree.close()
    cards = [x for x in tree.root.all() if x.has('detail-item')]
    if len(cards) > 1000:
        raise SourceError('На сторінці забагато карток')
    rows, errors = [], 0
    for card in cards:
        try:
            area = card.find(cls='detail-item-title')
            anchor = area.find(tag='a', attr='href') if area else None
            if anchor is None:
                raise ValueError('Не знайдено посилання на товар')
            title = area.text()
            article = oem = ''
            props = card.find(cls='detail-item-chars')
            for item in props.all() if props else []:
                if item.tag != 'small':
                    continue
                bold = item.find(tag='b')
                if bold is None:
                    continue
                label, value = item.text().lower(), bold.text()
                if 'арт' in label:
                    if article and article != value:
                        raise ValueError('Різні артикули')
                    article = value
                elif 'ориг' in label or 'oem' in label:
                    if oem and oem != value:
                        raise ValueError('Різні OEM')
                    oem = value
            if not article or not title:
                raise ValueError('Немає артикула або назви')
            if '\ufffd' in article or '\ufffd' in title or '\ufffd' in oem:
                raise ValueError('Пошкоджене кодування в критичних полях товару')
            category = subcategory = ''
            script = card.find(tag='script')
            if script:
                for key in ('item_category2', 'item_category3'):
                    found = re.search(r'\b' + key + r'\s*:\s*([\'\"])(.*?)\1', script.text())
                    if found:
                        if key == 'item_category2':
                            category = clean(found.group(2))
                        else:
                            subcategory = clean(found.group(2))
            uah, usd = card.find(cls='detail-item-uprice'), card.find(cls='detail-item-price')
            part_link = source_url(anchor.attrs['href'], url)
            condition = card.find(cls='detail-item-labels')
            rows.append(dict(source_article=article, oem=oem, part_name=title,
                             price_uah=price_text(uah.text(), 'uah') if uah else '',
                             price_usd=price_text(usd.text(), 'usd') if usd else '',
                             category=category, subcategory=subcategory,
                             condition=condition.text() if condition else '',
                             source_url=part_link, source_page=url,
                             observed_at=datetime.now(timezone.utc).isoformat()))
        except (ValueError, KeyError, TypeError):
            errors += 1
    # Parse catalogue navigation independently from product card HTML. Aleto
    # mixes /car/ and /ua/car/ paths, and category/page links can be outside
    # product-card containers.
    class CatalogueLinks(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.urls = []
            self.bad = 0

        def handle_starttag(self, tag, attrs):
            if tag != 'a' or len(self.urls) >= 1500:
                return
            options = dict(attrs)
            href = options.get('href')
            if not href:
                return
            rel = options.get('rel', '')
            classes = options.get('class', '').split()
            if not ('detail-cat-item' in classes or 'next' in rel.split()
                    or re.search(r'(?:page-\d+|[?&](?:page|PAGEN_\d+)=\d+|/page/\d+)', href, re.I)):
                return
            try:
                candidate = source_url(href, url)
                if within_catalogue(candidate, url) and candidate not in self.urls:
                    self.urls.append(candidate)
            except ValueError:
                self.bad += 1

    collector = CatalogueLinks()
    collector.feed(html)
    collector.close()
    links = collector.urls
    errors += collector.bad
    if not cards and not links:
        raise SourceError('UNRECOGNIZED_OR_EMPTY_HTML: жодних товарів або посилань')
    return rows, links, errors, len(cards)


def connect_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    fresh = not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
    if fresh:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manufacturer TEXT NOT NULL, model TEXT NOT NULL, year INTEGER,
            generation TEXT NOT NULL, catalogue TEXT NOT NULL,
            status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pages (
            job_id INTEGER NOT NULL REFERENCES jobs(id), url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued', errors INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(job_id,url)
        );
        CREATE TABLE IF NOT EXISTS parts (
            job_id INTEGER NOT NULL REFERENCES jobs(id), page TEXT NOT NULL,
            article TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(job_id,page,article)
        );
        CREATE INDEX IF NOT EXISTS parts_by_job ON parts(job_id);
    ''')
    local_store.migrate(con, DB_PATH, fresh=fresh)
    return con


def job_stats(con, job_id):
    p = con.execute('SELECT COUNT(*) AS n FROM parts WHERE job_id=?', (job_id,)).fetchone()['n']
    data = con.execute('SELECT payload FROM parts WHERE job_id=?', (job_id,)).fetchall()
    seen = set()
    price_count, oem_count, ready = 0, 0, 0
    for item in data:
        row = json.loads(item['payload'])
        if row['source_article'] not in seen:
            seen.add(row['source_article'])
            price_count += int(bool(row['price_uah'] or row['price_usd']))
            oem_count += int(bool(row['oem']))
        ready += int(bool(row['category'] and row['subcategory']))
    pages = con.execute('SELECT status,COUNT(*) AS n FROM pages WHERE job_id=? GROUP BY status', (job_id,)).fetchall()
    counts = {x['status']: x['n'] for x in pages}
    return {'records': p, 'unique': len(seen), 'prices': price_count, 'oem': oem_count,
            'ready': ready, 'pages': counts}


def _csv_cell(value):
    v = '' if value is None else str(value)
    if v.lstrip()[:1] in ('=', '+', '-', '@') or v.startswith(('\t', '\r', '\n')):
        return "'" + v
    return v


def build_export_row(record, job):
    provenance = {
        'article': record['source_article'],
        'title': record['part_name'], 'oem': record['oem'],
        'category': record['category'], 'subcategory': record['subcategory'],
        'source_page': record['source_page'], 'checked_at': record['observed_at'],
        'data_origin': record.get('data_origin', 'public_html_local'), 'parser': VERSION,
    }
    if job['year']:
        provenance['selected_year'] = str(job['year'])
    return {
        'schema_version': '2', 'source': 'aleto',
        'source_article': record['source_article'],
        'manufacturer': job['manufacturer'], 'model': job['model'],
        'generation': job['generation'], 'year_from': '', 'year_to': '',
        'category': record['category'], 'subcategory': record['subcategory'],
        'part_name': record['part_name'], 'oem': record['oem'],
        'condition': record['condition'], 'side': '', 'position': '',
        'price_uah': record['price_uah'], 'price_usd': record['price_usd'],
        'source_url': record['source_url'], 'observed_at': record['observed_at'],
        'source_record': json.dumps(provenance, ensure_ascii=False, separators=(',', ':')),
    }


def export_csv(job_id, directory):
    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    con = connect_db()
    try:
        job = con.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not job:
            raise ValueError('Завдання не знайдено')
        records = con.execute('SELECT payload FROM parts WHERE job_id=? ORDER BY rowid', (job_id,)).fetchall()
        ready, rejected = [], []
        for item in records:
            value = json.loads(item['payload'])
            if not value['category'] or not value['subcategory']:
                rejected.append(value)
            else:
                ready.append(build_export_row(value, job))
        if not ready:
            raise ValueError('Немає записів із повною категорією та підкатегорією для імпорту')
        slug = re.sub(r'[^A-Za-z0-9_-]', '-', f"{job['manufacturer']}-{job['model']}-{job['year'] or 'all'}")[:85]
        names = []
        import io
        current = []
        current_bytes = 3  # UTF-8 BOM
        header_buf = io.StringIO(newline='')
        csv.writer(header_buf).writerow(CSV_COLUMNS)
        header_bytes = len(header_buf.getvalue().encode('utf-8'))
        current_bytes += header_bytes

        def encode_row(row):
            output = io.StringIO(newline='')
            writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
            writer.writerow({k: _csv_cell(row[k]) for k in CSV_COLUMNS})
            return len(output.getvalue().encode('utf-8'))

        def flush():
            nonlocal current_bytes
            if not current:
                return
            output = dest / f'CarPot-Aleto-{slug}-{len(names)+1:03}.csv'
            with output.open('w', encoding='utf-8-sig', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                for row in current:
                    writer.writerow({k: _csv_cell(row[k]) for k in CSV_COLUMNS})
            names.append(output)
            current.clear()
            current_bytes = 3 + header_bytes

        for value in ready:
            size = encode_row(value)
            if size + 3 + header_bytes > MAX_CSV_BYTES:
                raise ValueError('Один запис перевищує ліміт файлу')
            if current and (len(current) >= MAX_CSV_ROWS or
                            current_bytes + size > MAX_CSV_BYTES):
                flush()
            current.append(value)
            current_bytes += size
        flush()
        if rejected:
            raw_path = dest / f'CarPot-Aleto-{slug}-needs-taxonomy.json'
            raw_path.write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding='utf-8')
        return names, len(ready), len(rejected)
    finally:
        con.close()


class MainWindow:
    def __init__(self, root):
        self.root = root
        root.title(f'{APP_NAME}  ·  {VERSION}')
        root.geometry('1280x780')
        root.minsize(980, 660)
        root.configure(bg=DARK)
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.job_id = None
        self.vehicle_id = None
        self.offset = 0
        self.query = tk.StringVar()
        self.category_filter = tk.StringVar()
        self.has_oem = tk.BooleanVar()
        self.has_price = tk.BooleanVar()
        self.sort_price = tk.BooleanVar()
        self.cancel_requested = False
        self.export_files = []
        self.brand = tk.StringVar()
        self.model = tk.StringVar()
        self.year = tk.StringVar()
        self.generation = tk.StringVar()
        self.catalogue = tk.StringVar()
        self.vin_candidate = None
        self.catalogue_client = CatalogueClient(DATA_DIR / 'catalogue_cache.sqlite3')
        self.oracle_candidate = None
        self.status = tk.StringVar(value='Готово до роботи')
        self.statistics = tk.StringVar(value='0 записів  ·  0 з ціною  ·  0 OEM')
        self._style()
        self._draw()
        self.clipboard_support = install_clipboard_support(root)
        self._load_last_job()
        self._load_vehicles()
        self._load_catalogues()
        self.root.after(150, self._poll)

    def _style(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Dark.TFrame', background=DARK)
        style.configure('Panel.TFrame', background=PANEL)
        style.configure('Dark.TLabel', background=PANEL, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('Title.TLabel', background=DARK, foreground=TEXT, font=('Segoe UI Semibold', 19))
        style.configure('Help.TLabel', background=PANEL, foreground=MUTED, font=('Segoe UI', 9))
        style.configure('Header.TLabel', background=PANEL, foreground=TEXT, font=('Segoe UI Semibold', 11))
        style.configure('Dark.TEntry', fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT, padding=6, borderwidth=0)
        style.configure('Dark.TCombobox', fieldbackground=FIELD, foreground=TEXT, background=FIELD, padding=5)
        style.map('Dark.TCombobox', fieldbackground=[('readonly', FIELD)], foreground=[('readonly', TEXT)])
        style.configure('Accent.TButton', background=ACCENT, foreground=DARK, font=('Segoe UI Semibold', 10), padding=9)
        style.map('Accent.TButton', background=[('active', '#31D5C5'), ('disabled', '#3E6E69')])
        style.configure('Quiet.TButton', background=FIELD, foreground=TEXT, padding=9)
        style.map('Quiet.TButton', background=[('active', '#375267'), ('disabled', '#29343F')])
        style.configure('Dark.Treeview', background=FIELD, foreground=TEXT, fieldbackground=FIELD,
                        borderwidth=0, rowheight=28, font=('Segoe UI', 9))
        style.configure('Dark.Treeview.Heading', background='#2C4052', foreground=TEXT, font=('Segoe UI Semibold', 9), relief='flat')
        style.map('Dark.Treeview', background=[('selected', '#127D78')])

    def _draw(self):
        """Compact workflow: vehicle -> catalogue -> collection -> export.

        Important actions live outside the center pane so they stay reachable
        even at the minimum window size and under Windows display scaling.
        """
        top = ttk.Frame(self.root, style='Dark.TFrame', padding=(18, 10, 18, 7))
        top.pack(fill='x')
        ttk.Label(top, text='CarPot  /  Local Aleto', style='Title.TLabel').pack(side='left')
        tk.Label(top, text='Власна база автомобілів і запчастин', bg=DARK, fg=MUTED,
                 font=('Segoe UI', 10)).pack(side='right')

        garage = ttk.Frame(self.root, style='Panel.TFrame', padding=(10, 7))
        garage.pack(fill='x', padx=14, pady=(0, 5))
        ttk.Label(garage, text='Мої автомобілі', style='Header.TLabel').pack(side='left', padx=(0, 8))
        self.vehicle_box = ttk.Combobox(garage, state='readonly', style='Dark.TCombobox', width=23)
        self.vehicle_box.pack(side='left', fill='x', expand=True)
        self.vehicle_box.bind('<<ComboboxSelected>>', self._select_vehicle)
        ttk.Button(garage, text='Додати за VIN', command=self._decode_vin,
                   style='Quiet.TButton').pack(side='left', padx=(8, 3))
        ttk.Button(garage, text='З каталогу CarPot', command=self._browse_catalogue,
                   style='Quiet.TButton').pack(side='left', padx=3)
        ttk.Button(garage, text='Зберегти авто', command=self._save_vehicle,
                   style='Accent.TButton').pack(side='left', padx=(4, 0))

        self.vehicle_details = tk.StringVar(value='Додайте авто через VIN або виберіть з каталогу CarPot')
        tk.Label(self.root, textvariable=self.vehicle_details, bg=DARK, fg=MUTED,
                 anchor='w', font=('Segoe UI', 9)).pack(fill='x', padx=20, pady=(0, 5))

        archives = ttk.Frame(self.root, style='Panel.TFrame', padding=(10, 5))
        archives.pack(fill='x', padx=14, pady=(0, 6))
        ttk.Label(archives, text='Зібрані каталоги моделей', style='Dark.TLabel').pack(side='left', padx=(0, 8))
        self.archive_box = ttk.Combobox(archives, state='readonly', style='Dark.TCombobox')
        self.archive_box.pack(side='left', fill='x', expand=True)
        self.archive_box.bind('<<ComboboxSelected>>', self._select_archive)
        ttk.Button(archives, text='Імпорт старої SQLite', command=self._import_database,
                   style='Quiet.TButton').pack(side='right', padx=(10, 0))

        center = ttk.Frame(self.root, style='Dark.TFrame', padding=(14, 0, 14, 7))
        # Pack the center LAST so fixed footer and actions reserve their space.
        left = ttk.Frame(center, style='Panel.TFrame', padding=12, width=355)
        left.pack(side='left', fill='y', padx=(0, 10))
        left.pack_propagate(False)
        right = ttk.Frame(center, style='Panel.TFrame', padding=12)
        right.pack(side='left', fill='both', expand=True)

        ttk.Label(left, text='1  Автомобіль', style='Header.TLabel').pack(anchor='w', pady=(0, 5))
        row1 = ttk.Frame(left, style='Panel.TFrame')
        row1.pack(fill='x')
        row1.columnconfigure(0, weight=1)
        row1.columnconfigure(1, weight=1)
        make = ttk.Frame(row1, style='Panel.TFrame')
        make.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        model = ttk.Frame(row1, style='Panel.TFrame')
        model.grid(row=0, column=1, sticky='ew', padx=(5, 0))
        self._field(make, 'Марка', self.brand)
        self._field(model, 'Модель', self.model)
        row2 = ttk.Frame(left, style='Panel.TFrame')
        row2.pack(fill='x', pady=(0, 5))
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)
        year = ttk.Frame(row2, style='Panel.TFrame')
        year.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        generation = ttk.Frame(row2, style='Panel.TFrame')
        generation.grid(row=0, column=1, sticky='ew', padx=(5, 0))
        self._field(year, 'Рік', self.year)
        self._field(generation, 'Покоління (за потреби)', self.generation)

        ttk.Separator(left, orient='horizontal').pack(fill='x', pady=(7, 9))
        ttk.Label(left, text='2  Каталог Aleto', style='Header.TLabel').pack(anchor='w')
        ttk.Label(left, text='Знайдіть каталог або вставте посилання /car/.../',
                  style='Help.TLabel', wraplength=320).pack(anchor='w', pady=(3, 4))
        ttk.Entry(left, textvariable=self.catalogue, style='Dark.TEntry').pack(fill='x')
        self.discover_btn = ttk.Button(left, text='Знайти каталоги для цього авто',
                                       command=self.find_catalogues, style='Quiet.TButton')
        self.discover_btn.pack(fill='x', pady=(8, 0))
        self.candidate_panel = ttk.Frame(left, style='Panel.TFrame')
        ttk.Label(self.candidate_panel, text='Виберіть знайдений каталог',
                  style='Help.TLabel').pack(anchor='w', pady=(2, 3))
        self.candidate_box = ttk.Combobox(self.candidate_panel, state='readonly',
                                          style='Dark.TCombobox')
        self.candidate_box.pack(fill='x')
        self.candidate_box.bind('<<ComboboxSelected>>', self.choose_candidate)
        # An empty combo looks like a broken progress/scroll bar on Windows.
        # Display it only when candidates have actually been found.
        self.workflow_hint = tk.StringVar(value='Після вибору каталогу натисніть «Почати парсинг» нижче.')
        ttk.Label(left, textvariable=self.workflow_hint, style='Help.TLabel',
                  wraplength=320).pack(anchor='w', pady=(9, 0))

        ttk.Label(right, text='Запчастини вибраного каталогу', style='Header.TLabel').pack(anchor='w')
        self.stats_label = tk.Label(right, textvariable=self.statistics, bg=PANEL, fg=ACCENT,
                                    font=('Segoe UI Semibold', 10), anchor='w')
        self.stats_label.pack(fill='x', pady=(3, 8))

        filters = ttk.Frame(right, style='Panel.TFrame')
        filters.pack(fill='x', pady=(0, 7))
        filters.columnconfigure(0, weight=3)
        filters.columnconfigure(1, weight=2)
        ttk.Label(filters, text='Пошук: назва / OEM / артикул',
                  style='Help.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(filters, text='Категорія', style='Help.TLabel').grid(
            row=0, column=1, sticky='w', padx=(7, 0))
        search = ttk.Entry(filters, textvariable=self.query, style='Dark.TEntry')
        search.grid(row=1, column=0, sticky='ew')
        search.bind('<Return>', lambda _event: self._filter())
        category = ttk.Entry(filters, textvariable=self.category_filter, style='Dark.TEntry')
        category.grid(row=1, column=1, sticky='ew', padx=(7, 0))
        category.bind('<Return>', lambda _event: self._filter())
        ttk.Button(filters, text='Застосувати', command=self._filter,
                   style='Quiet.TButton').grid(row=1, column=2, padx=(7, 0))
        selections = ttk.Frame(right, style='Panel.TFrame')
        selections.pack(fill='x', pady=(0, 6))
        ttk.Checkbutton(selections, text='Лише з OEM', variable=self.has_oem,
                        command=self._filter).pack(side='left')
        ttk.Checkbutton(selections, text='Лише з ціною', variable=self.has_price,
                        command=self._filter).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(selections, text='Сортувати за ціною', variable=self.sort_price,
                        command=self._filter).pack(side='left', padx=(10, 0))
        ttk.Button(selections, text='Скинути фільтри', command=self._reset_filters,
                   style='Quiet.TButton').pack(side='right')

        table_area = ttk.Frame(right, style='Panel.TFrame')
        table_area.pack(fill='both', expand=True)
        table_area.rowconfigure(0, weight=1)
        table_area.columnconfigure(0, weight=1)
        cols = ('article', 'name', 'oem', 'price', 'tax')
        self.table = ttk.Treeview(table_area, columns=cols, show='headings', style='Dark.Treeview')
        definitions = [('article', 'Артикул', 82), ('name', 'Назва запчастини', 290),
                       ('oem', 'OEM', 105), ('price', 'Ціна', 105), ('tax', 'Категорія', 125)]
        for key, title, width in definitions:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor='w', minwidth=55,
                              stretch=(key == 'name'))
        vertical = ttk.Scrollbar(table_area, orient='vertical', command=self.table.yview)
        horizontal = ttk.Scrollbar(table_area, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.table.bind('<Double-1>', self._open_part)
        pager = ttk.Frame(right, style='Panel.TFrame')
        pager.pack(fill='x', pady=(5, 0))
        ttk.Button(pager, text='← Назад', command=lambda: self._page(-100),
                   style='Quiet.TButton').pack(side='left')
        self.next_page = ttk.Button(pager, text='Далі →', command=lambda: self._page(100),
                                    style='Quiet.TButton')
        self.next_page.pack(side='left', padx=5)
        ttk.Button(pager, text='Історія цін', command=self._history,
                   style='Quiet.TButton').pack(side='right')

        # Fixed action bar: never clipped by the vehicle form or long logs.
        actions = ttk.Frame(self.root, style='Panel.TFrame', padding=(12, 8))
        ttk.Label(actions, text='3  Дії', style='Header.TLabel').pack(side='left', padx=(0, 8))
        self.start_btn = ttk.Button(actions, text='▶ Почати парсинг', command=self.start,
                                    style='Accent.TButton')
        self.start_btn.pack(side='left', padx=(0, 5))
        self.update_btn = ttk.Button(actions, text='Оновити ціни',
                                     command=lambda: self.start(update_prices=True),
                                     style='Quiet.TButton')
        self.update_btn.pack(side='left', padx=(0, 4))
        self.pause_btn = ttk.Button(actions, text='Пауза', command=self.pause,
                                    style='Quiet.TButton')
        self.pause_btn.pack(side='left', padx=(0, 4))
        self.cancel_btn = ttk.Button(actions, text='Зупинити', command=self.cancel,
                                     style='Quiet.TButton')
        self.cancel_btn.pack(side='left')
        self.upload_btn = ttk.Button(actions, text='Імпорт у CarPot', command=self.open_carpot,
                                     style='Quiet.TButton')
        self.upload_btn.pack(side='right')
        self.export_btn = ttk.Button(actions, text='Підготувати CSV', command=self.export,
                                     style='Accent.TButton')
        self.export_btn.pack(side='right', padx=(0, 6))
        self.pause_btn.state(['disabled'])
        self.cancel_btn.state(['disabled'])

        bottom = ttk.Frame(self.root, style='Panel.TFrame', padding=(12, 7))
        bottom.pack(side='bottom', fill='x', padx=14, pady=(0, 10))
        actions.pack(side='bottom', fill='x', padx=14, pady=(0, 5))
        center.pack(side='top', fill='both', expand=True)
        bottom_bar = ttk.Frame(bottom, style='Panel.TFrame')
        bottom_bar.pack(fill='x')
        ttk.Label(bottom_bar, text='Стан:', style='Header.TLabel').pack(side='left', padx=(0, 6))
        tk.Label(bottom_bar, textvariable=self.status, bg=PANEL, fg=ACCENT, anchor='w',
                 font=('Segoe UI Semibold', 10)).pack(side='left', fill='x', expand=True)
        ttk.Button(bottom_bar, text='Журнал ▾', command=self._toggle_log,
                   style='Quiet.TButton').pack(side='right')
        self.progress = ttk.Progressbar(bottom, mode='indeterminate')
        self.progress.pack(fill='x', pady=(5, 0))
        self.log = tk.Text(bottom, height=3, bg=FIELD, fg=MUTED,
                           font=('Consolas', 9), relief='flat', wrap='word', state='disabled')
        self.log_visible = False
        self._log('Програма готова. Дані зберігаються локально в ' + str(DATA_DIR))

    def _toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log.pack(fill='x', pady=(6, 0))
        else:
            self.log.pack_forget()

    def _reset_filters(self):
        self.query.set('')
        self.category_filter.set('')
        self.has_oem.set(False)
        self.has_price.set(False)
        self.sort_price.set(False)
        self._filter()

    def _field(self, parent, name, var):
        ttk.Label(parent, text=name, style='Dark.TLabel').pack(anchor='w', pady=(6, 3))
        ttk.Entry(parent, textvariable=var, style='Dark.TEntry').pack(fill='x')

    def _log(self, message):
        self.log.configure(state='normal')
        self.log.insert('end', datetime.now().strftime('%H:%M:%S') + '  ' + message + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def _set_busy(self, busy):
        self.busy = busy
        self.progress.start(15) if busy else self.progress.stop()
        state = 'disabled' if busy else 'normal'
        self.start_btn.configure(state=state)
        self.discover_btn.configure(state=state)
        self.export_btn.configure(state=state)
        self.update_btn.configure(state=state)
        self.pause_btn.configure(state='normal' if busy else 'disabled')
        self.cancel_btn.configure(state='normal' if busy else 'disabled')

    def _vehicle(self):
        make = clean(self.brand.get())
        model = clean(self.model.get())
        if not make or not model:
            raise ValueError('Вкажи марку і модель автомобіля')
        yr = clean(self.year.get())
        year = int(yr) if yr else None
        if year and not 1886 <= year <= 2100:
            raise ValueError('Рік має бути в межах 1886–2100')
        return make, model, year, clean(self.generation.get())

    def find_catalogues(self):
        if self.busy:
            return
        try:
            make, model, year, gen = self._vehicle()
        except (ValueError, TypeError) as exc:
            messagebox.showerror('CarPot', str(exc))
            return
        self.stop.clear()
        self._set_busy(True)
        self.status.set('Пошук каталогів Aleto…')
        self.candidate_panel.pack_forget()
        self.candidate_box['values'] = ()
        def task():
            try:
                source = SourceClient(self.stop)
                found = set()
                for sitemap in SITEMAPS:
                    raw = source.read(sitemap, MAX_BYTES_SITEMAP, ('text/xml', 'application/xml'))
                    found.update(find_candidates(raw, make, model, year, gen))
                if not found:
                    # Aleto's manufacturer directory may list models omitted by sitemaps.
                    brand_url = f'https://aleto.ua/ua/mark/{_make_slug(make)}/'
                    try:
                        page = source.read(brand_url, 2 * 1024 * 1024, ('text/html',))
                        found.update(find_brand_page_candidates(page, brand_url, make, model, year, gen))
                    except (SourceError, UnicodeError, ValueError) as exc:
                        # Searching is advisory; the user can still paste a valid
                        # catalogue URL manually without losing the vehicle.
                        self.events.put(('status', 'Сторінка марки недоступна: ' + str(exc)[:100]))
                self.events.put(('candidates', sorted(found)))
            except InterruptedError:
                self.events.put(('status', 'Пошук зупинено'))
            except Exception as exc:
                self.events.put(('error', str(exc)))
            finally:
                self.events.put(('busy', False))
        threading.Thread(target=task, daemon=True).start()

    def choose_candidate(self, _event=None):
        value = self.candidate_box.get()
        if value:
            self.catalogue.set(value)

    def start(self, *, update_prices=False):
        if self.busy:
            return
        try:
            make, model, year, gen = self._vehicle()
            url = catalogue_url(clean(self.catalogue.get()))
        except (ValueError, TypeError) as exc:
            messagebox.showerror('CarPot', str(exc))
            return
        self.stop.clear()
        self.cancel_requested = False
        current_job = self.job_id
        vehicle_id = None
        selected = next((row for row in self.vehicles if row['id'] == self.vehicle_id), None)
        if selected and (selected['manufacturer'], selected['model'], selected['year'], selected['generation']) == (make, model, year, gen):
            vehicle_id = self.vehicle_id
        self._set_busy(True)
        self.status.set('Збір запчастин…')
        self.workflow_hint.set('Збір активний. Прогрес і кількість деталей видно в таблиці праворуч.')
        def task():
            try:
                con = connect_db()
                try:
                    if update_prices:
                        previous = con.execute('''SELECT * FROM jobs WHERE id=? AND catalogue=? AND manufacturer=?
                                                   AND model=? AND year IS ? AND generation=? AND vehicle_id IS ?''',
                                               (current_job, url, make, model, year, gen, vehicle_id)).fetchone()
                        if not previous:
                            raise ValueError('Відкрийте збережений збір для цього автомобіля')
                        with con:
                            changed = con.execute("UPDATE pages SET status='queued' WHERE job_id=? AND status='done'",
                                                  (previous['id'],)).rowcount
                            if not changed:
                                raise ValueError('У завданні ще немає перевірених сторінок')
                            con.execute("UPDATE jobs SET status='queued' WHERE id=?", (previous['id'],))
                    existing = con.execute('''SELECT * FROM jobs WHERE catalogue=? AND manufacturer=? AND model=?
                                               AND COALESCE(year,0)=? AND generation=?
                                               AND vehicle_id IS ? AND status IN ('paused','failed','queued','completed','partial','limited')
                                               ORDER BY id DESC LIMIT 1''', (url, make, model, year or 0, gen, vehicle_id)).fetchone()
                    if update_prices:
                        existing = previous
                    if existing:
                        job_id = existing['id']
                        con.execute('UPDATE jobs SET status=?, error=? WHERE id=?', ('queued', '', job_id))
                        con.execute("UPDATE pages SET status='queued' WHERE job_id=? AND status='failed'", (job_id,))
                        if not update_prices and existing['status'] in ('completed', 'partial', 'limited'):
                            # Reopen the root: detect pages previously missed, keep parts.
                            con.execute("UPDATE pages SET status='queued' WHERE job_id=? AND url=?",
                                        (job_id, url))
                            self.events.put(('log', 'Пошук пропущених сторінок у збереженому зборі'))
                        self.events.put(('log', f'Відновлення завдання #{job_id}'))
                    else:
                        job_id = con.execute('''INSERT INTO jobs(manufacturer,model,year,generation,catalogue,status,created_at,vehicle_id)
                                                VALUES (?,?,?,?,?,?,?,?)''',
                                             (make, model, year, gen, url, 'queued',
                                              datetime.now(timezone.utc).isoformat(), vehicle_id)).lastrowid
                        con.execute('INSERT INTO pages(job_id,url) VALUES (?,?)', (job_id, url))
                        self.events.put(('log', f'Нове завдання #{job_id}'))
                    con.commit()
                    self.events.put(('job', job_id))
                    source = SourceClient(self.stop)
                    hit_page_limit = False
                    while not self.stop.is_set():
                        page = con.execute("SELECT url FROM pages WHERE job_id=? AND status='queued' ORDER BY rowid LIMIT 1", (job_id,)).fetchone()
                        if page is None:
                            break
                        page_url = page['url']
                        self.events.put(('status', 'Обробка: ' + urlsplit(page_url).path))
                        raw = source.read(page_url, MAX_BYTES_PAGE, ('text/html',))
                        data, encoding_warnings = decode_html_page(raw)
                        records, links, errors, cards = extract_page(data, page_url)
                        errors += encoding_warnings
                        if encoding_warnings:
                            self.events.put(('log',
                                f'Увага: сторінка містить {encoding_warnings} некоректних '
                                'символів; збережені записи позначено для перевірки'))
                        with con:
                            for record in records:
                                local_store.record_prices(con, job_id, record)
                                con.execute('''INSERT INTO parts(job_id,page,article,payload) VALUES (?,?,?,?)
                                               ON CONFLICT(job_id,page,article) DO UPDATE SET payload=excluded.payload''',
                                            (job_id, page_url, record['source_article'],
                                             json.dumps(record, ensure_ascii=False)))
                            for link in links:
                                if not update_prices and within_catalogue(link, url):
                                    exists = con.execute('SELECT 1 FROM pages WHERE job_id=? AND url=?',
                                                         (job_id, link)).fetchone()
                                    if exists:
                                        continue
                                    count = con.execute('SELECT COUNT(*) FROM pages WHERE job_id=?', (job_id,)).fetchone()[0]
                                    if count >= MAX_PAGES:
                                        hit_page_limit = True
                                        break
                                    con.execute('INSERT OR IGNORE INTO pages(job_id,url) VALUES (?,?)', (job_id, link))
                            con.execute('UPDATE pages SET status=?, errors=? WHERE job_id=? AND url=?',
                                        ('done', errors, job_id, page_url))
                        stats = job_stats(con, job_id)
                        self.events.put(('stats', stats))
                        self.events.put(('log', f'{cards} карток; {len(records)} записів; '
                                                f'{len(links)} посилань на сторінки/категорії; '
                                                f'сторінок {stats["pages"].get("done", 0)}; '
                                                f'артикулів {stats["unique"]}'))
                        self.events.put(('refresh', None))
                        if not update_prices and stats['records'] >= MAX_RECORDS:
                            self.events.put(('log', 'Досягнуто ліміт записів; збір зупинено'))
                            break
                    with con:
                        if self.stop.is_set():
                            status, error = ('cancelled' if self.cancel_requested else 'paused'), ''
                        else:
                            pending = con.execute("SELECT COUNT(*) FROM pages WHERE job_id=? AND status='queued'", (job_id,)).fetchone()[0]
                            faults = con.execute('SELECT COALESCE(SUM(errors),0) FROM pages WHERE job_id=?', (job_id,)).fetchone()[0]
                            status = 'limited' if hit_page_limit or pending else ('partial' if faults else 'completed')
                            error = 'Деякі сторінки або записи потребують перевірки' if status == 'partial' else ''
                        con.execute('UPDATE jobs SET status=?,error=? WHERE id=?', (status, error, job_id))
                    self.events.put(('status', 'Збір: ' + JOB_STATUS.get(status, status)))
                finally:
                    con.close()
            except InterruptedError:
                status = 'cancelled' if self.cancel_requested else 'paused'
                if 'job_id' in locals():
                    with closing(connect_db()) as db, db:
                        db.execute('UPDATE jobs SET status=? WHERE id=?', (status, job_id))
                self.events.put(('status', JOB_STATUS[status]))
            except Exception as exc:
                self.events.put(('error', str(exc)))
                # Failure is not retried automatically; Cloudflare 403 is terminal until operator action.
                try:
                    with closing(connect_db()) as con, con:
                        if 'job_id' in locals():
                            con.execute('UPDATE jobs SET status=?,error=? WHERE id=?', ('failed', str(exc)[:300], job_id))
                except Exception:
                    pass
            finally:
                self.events.put(('refresh', None))
                self.events.put(('busy', False))
        threading.Thread(target=task, daemon=True).start()

    def pause(self):
        self.stop.set()
        self.status.set('Призупинення після поточного запиту…')

    def cancel(self):
        if self.busy:
            self.cancel_requested = True
            self.stop.set()

    def _browse_catalogue(self):
        if not self.busy:
            CatalogueDialog(self)

    def _clear_previous_catalogue(self):
        """Don't show parts of the previous car while decoding a different VIN."""
        self.job_id = None
        self.vehicle_id = None
        self.vehicle_box.set('')
        self.archive_box.set('')
        self.visible_urls = {}
        self._refresh()

    def apply_catalogue(self, kind, make, model, modification, year):
        self._clear_previous_catalogue()
        proposed = (make['name'], model['name'], year)
        self.oracle_candidate = (proposed, modification['id'], modification['name'], kind)
        if self.vin_candidate:
            _, decoded, _ = self.vin_candidate
            if (clean(decoded['Make']).casefold(), clean(decoded['Model']).casefold()) != (
                    clean(make['name']).casefold(), clean(model['name']).casefold()):
                self.vin_candidate = None
        self.brand.set(make['name'])
        self.model.set(model['name'])
        self.year.set(year)
        self.generation.set('')
        self.catalogue.set('')
        self.vehicle_details.set(f"Oracle · {modification['name']} · #{modification['id']} · вибір користувача")
        self.status.set('Перевірте дані та натисніть «Зберегти авто»')

    def _decode_vin(self):
        if self.busy:
            return
        from_carpot = self.catalogue_client.connected
        provider = 'CarPot' if from_carpot else 'NHTSA vPIC'
        raw = simpledialog.askstring(APP_NAME, f'Введіть VIN для пошуку · {provider}')
        if not raw:
            return
        vin = raw.strip().upper()
        if not re.fullmatch('[A-HJ-NPR-Z0-9]{17}', vin):
            messagebox.showerror(APP_NAME, 'VIN має містити 17 символів без I, O, Q')
            return
        self.vin_candidate = None
        self.oracle_candidate = None
        self._set_busy(True)
        self.status.set(f'Читання VIN · {provider}…')

        def task():
            try:
                if from_carpot:
                    decoded = self.catalogue_client.decode(vin)
                    row = {target: decoded.get(source) for target, source in {
                        'Make': 'manufacturer', 'Model': 'model', 'ModelYear': 'year', 'EngineModel': 'engine',
                        'DisplacementL': 'engine_displacement_l', 'FuelTypePrimary': 'fuel_type',
                        'DriveType': 'drive_type', 'TransmissionStyle': 'transmission',
                    }.items()}
                    self.events.put(('vin', (vin, row, 'carpot_vin')))
                    return
                url = f'https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json'
                with urlopen(Request(url, headers={'User-Agent': USER_AGENT}), timeout=10) as response:
                    row = json.loads(response.read(256_000))['Results'][0]
                if not row['Make'] or not row['Model']:
                    raise ValueError('NHTSA не визначив марку або модель')
                self.events.put(('vin', (vin, row, 'nhtsa_vpic')))
            except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
                retry = ' Якщо сесію завершено, повторіть пошук через NHTSA vPIC.' if from_carpot else ''
                self.events.put(('error', 'VIN не вдалося розпізнати. Введіть характеристики вручну.' + retry))
            finally:
                self.events.put(('busy', False))
        threading.Thread(target=task, daemon=True).start()

    def _import_database(self):
        if self.busy:
            return
        name = filedialog.askopenfilename(title='Виберіть закриту копію SQLite v1.0', filetypes=[('SQLite', '*.sqlite3 *.db')])
        if not name:
            return
        if Path(name).resolve() == DB_PATH.resolve():
            messagebox.showinfo(APP_NAME, 'Ця база вже відкрита у програмі')
            return
        self._set_busy(True)
        self.status.set('Перенесення SQLite…')

        def task():
            try:
                db = connect_db()
                try:
                    result = local_store.import_v1(db, name)
                finally:
                    db.close()
                self.events.put(('imported', result))
            except (ValueError, OSError, sqlite3.Error) as error:
                self.events.put(('error', str(error)))
            finally:
                self.events.put(('busy', False))
        threading.Thread(target=task, daemon=True).start()

    def _open_part(self, _event=None):
        selection = self.table.selection()
        if selection:
            url = self.visible_urls.get(selection[0])
            if url:
                webbrowser.open(url)

    def _load_vehicles(self):
        with closing(connect_db()) as db, db:
            self.vehicles = db.execute('SELECT * FROM vehicles ORDER BY manufacturer, model, year, id').fetchall()
        self.vehicle_box['values'] = [
            f'{row["manufacturer"]} {row["model"]} {row["year"] or ""} · #{row["id"]}'
            for row in self.vehicles
        ]
        for index, row in enumerate(self.vehicles):
            if row['id'] == self.vehicle_id:
                self.vehicle_box.current(index)
                self._describe_vehicle(row)
                break

    def _save_vehicle(self):
        if self.busy:
            return
        try:
            make, model, year, generation = self._vehicle()
            with closing(connect_db()) as db, db:
                details = {}
                if self.vin_candidate:
                    vin, decoded, provider = self.vin_candidate
                    same_vehicle = (make.casefold(), model.casefold()) == (
                        clean(decoded['Make']).casefold(), clean(decoded['Model']).casefold(),
                    )
                    if same_vehicle:
                        details = dict(vin=vin, source=provider + '_reviewed', engine=decoded.get('EngineModel') or None,
                                       displacement=decoded.get('DisplacementL') or None, fuel=decoded.get('FuelTypePrimary') or None,
                                       drive=decoded.get('DriveType') or None, transmission=decoded.get('TransmissionStyle') or None)
                if self.oracle_candidate:
                    vehicle, modification_id, description, kind = self.oracle_candidate
                    if (make, model, str(year or '')) == vehicle:
                        details.update(modification=description, source_modification_id=modification_id)
                        details['source'] = details.get('source', 'manual') + '+oracle_' + kind
                self.vehicle_id = local_store.add_vehicle(db, make, model, year, generation, **details)
                self.vin_candidate = None
                self.oracle_candidate = None
            saved_catalogue = self.catalogue.get()
            self._load_vehicles()
            self._select_vehicle()
            if not self.job_id:
                self.catalogue.set(saved_catalogue)
            self.status.set('Автомобіль збережено у «Мої автомобілі».')
            self.workflow_hint.set('Далі: знайдіть каталог Aleto та натисніть «Почати парсинг».')
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror(APP_NAME, str(error))

    def _describe_vehicle(self, row):
        values = [row['manufacturer'], row['model'], row['year'], row['generation'], row['modification'],
                  row['engine'], row['fuel'], row['drive'], row['transmission'], row['vin']]
        if row['source_modification_id']:
            values.append(f"Oracle #{row['source_modification_id']} · вибір користувача")
        self.vehicle_details.set(' · '.join(str(value) for value in values if value))

    def _select_vehicle(self, _event=None):
        if self.busy or self.vehicle_box.current() < 0:
            return
        row = self.vehicles[self.vehicle_box.current()]
        self.vin_candidate = None
        self.oracle_candidate = None
        self.vehicle_id = row['id']
        self.brand.set(row['manufacturer'])
        self.model.set(row['model'])
        self.generation.set(row['generation'])
        self.year.set(str(row['year'] or ''))
        with closing(connect_db()) as db, db:
            job = db.execute('SELECT * FROM jobs WHERE vehicle_id=? ORDER BY id DESC LIMIT 1',
                             (self.vehicle_id,)).fetchone()
        self.job_id = job['id'] if job else None
        self.catalogue.set(job['catalogue'] if job else '')
        self.status.set(JOB_STATUS.get(job['status'], job['status']) if job else 'Збір ще не запускався')
        self._describe_vehicle(row)
        self._filter()

    def _filter(self):
        self.offset = 0
        self._refresh()

    def _page(self, step):
        self.offset = max(0, self.offset + step)
        self._refresh()

    def _history(self):
        selection = self.table.selection()
        if not self.job_id or not selection:
            return
        article = self.table.item(selection[0], 'values')[0]
        with closing(connect_db()) as db, db:
            rows = db.execute('''SELECT observed_at, currency, price FROM price_history
                                 WHERE job_id=? AND article=? ORDER BY observed_at DESC LIMIT 25''',
                              (self.job_id, article)).fetchall()
        summary = '\n'.join(f'{row[0]} · {row[2]} {row[1]}' for row in rows)
        messagebox.showinfo(f'Історія: {article}', summary or 'Немає спостережень')

    def _load_catalogues(self):
        with closing(connect_db()) as db, db:
            self.catalogues = db.execute('SELECT * FROM jobs WHERE vehicle_id IS NULL ORDER BY id DESC').fetchall()
        self.archive_box.configure(values=[
            f'{row["manufacturer"]} {row["model"]} · #{row["id"]} · {JOB_STATUS.get(row["status"], row["status"])}'
            for row in self.catalogues
        ])
        for index, row in enumerate(self.catalogues):
            if row['id'] == self.job_id:
                self.archive_box.current(index)
                break

    def _select_archive(self, _event=None):
        index = self.archive_box.current()
        if self.busy or index < 0:
            return
        self.vehicle_id = None
        self.vehicle_box.set('')
        self.vehicle_details.set('Каталог моделі · сумісність із VIN не підтверджено')
        row = self.catalogues[index]
        self.vin_candidate = self.oracle_candidate = None
        self.job_id = row['id']
        for attr, key in [('brand', 'manufacturer'), ('model', 'model'),
                          ('generation', 'generation'), ('catalogue', 'catalogue')]:
            getattr(self, attr).set(row[key])
        self.year.set(str(row['year'] or ''))
        self.status.set(JOB_STATUS.get(row['status'], row['status']))
        self._filter()

    def _load_last_job(self):
        try:
            with closing(connect_db()) as con, con:
                job = con.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 1').fetchone()
            if job:
                self.job_id = job['id']
                self.vehicle_id = job['vehicle_id']
                for attr, key in [('brand', 'manufacturer'), ('model', 'model'),
                                  ('generation', 'generation'), ('catalogue', 'catalogue')]:
                    getattr(self, attr).set(job[key])
                self.year.set(str(job['year'] or ''))
                self.status.set(JOB_STATUS.get(job["status"], job["status"]))
                self._refresh()
        except sqlite3.Error as exc:
            self._log('Помилка читання локальної бази: ' + str(exc))

    def _refresh(self):
        if not self.job_id:
            self.table.delete(*self.table.get_children())
            self.statistics.set('Каталог порожній')
            self.next_page.state(['disabled'])
            return
        try:
            with closing(connect_db()) as con, con:
                stats = job_stats(con, self.job_id)
                rows = local_store.search(con, self.job_id, self.query.get(), self.category_filter.get(),
                                          self.has_oem.get(), self.has_price.get(), self.sort_price.get(), self.offset)
            self.next_page.state(['!disabled'] if len(rows) > 100 else ['disabled'])
            self._show_stats(stats)
            for node in self.table.get_children():
                self.table.delete(node)
            self.visible_urls = {}
            for item in rows[:100]:
                r = json.loads(item['payload'])
                row = self.table.insert('', 'end', values=(r['source_article'], r['part_name'],
                            r['oem'], (f'{r["price_uah"]} UAH' if r['price_uah'] else
                                       f'{r["price_usd"]} USD' if r['price_usd'] else ''), r['category']))
                try:
                    self.visible_urls[row] = source_url(r['source_url'])
                except ValueError:
                    pass
        except sqlite3.Error as exc:
            self._log('Помилка читання записів: ' + str(exc))

    def _show_stats(self, s):
        self.statistics.set(f"Пропозицій: {s['records']}  ·  Унікальних: {s['unique']}  ·  "
                            f"З ціною: {s['prices']}  ·  OEM: {s['oem']}  ·  "
                            f"Готових для CSV: {s['ready']}  ·  Сторінок: {s['pages'].get('done',0)}")

    def export(self):
        if self.busy:
            return
        if not self.job_id:
            messagebox.showinfo('CarPot', 'Спочатку запусти збір запчастин')
            return
        directory = filedialog.askdirectory(title='Куди зберегти CSV для CarPot?', initialdir=str(Path.home()))
        if not directory:
            return
        self._set_busy(True)
        self.status.set('Підготовка CSV…')
        def task():
            try:
                files, valid, invalid = export_csv(self.job_id, directory)
                self.events.put(('export', (files, valid, invalid)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
            finally:
                self.events.put(('busy', False))
        threading.Thread(target=task, daemon=True).start()

    def open_carpot(self):
        webbrowser.open(CARPOT_URL)
        if self.export_files:
            file = self.export_files[0]
            self.root.clipboard_clear()
            self.root.clipboard_append(str(file))
            self.root.update()
            if os.name == 'nt':
                import subprocess
                subprocess.Popen(['explorer.exe', '/select,', str(file)])
            self._log('Відкрито CarPot; шлях першого CSV скопійовано. Вибери файл у формі імпорту.')
        else:
            self._log('Відкрито CarPot. Спочатку натисни «Підготувати CSV».')

    def _poll(self):
        try:
            while True:
                action, payload = self.events.get_nowait()
                if action == 'busy':
                    self._set_busy(payload)
                    if not payload:
                        self._load_catalogues()
                elif action == 'candidates':
                    self.candidate_box['values'] = payload
                    if payload:
                        self.candidate_panel.pack(fill='x', pady=(6, 0))
                        self.candidate_box.current(0)
                        self.choose_candidate()
                        self._log(f'Знайдено каталогів: {len(payload)}. Перевір вибраний.')
                        self.status.set('Каталог знайдено — можна почати збір')
                        self.workflow_hint.set('Наступний крок: натисніть «Почати парсинг» у панелі дій.')
                    else:
                        self.candidate_panel.pack_forget()
                        self.workflow_hint.set('Каталог Aleto не знайдено. Спробуйте вручну вставити URL /car/.../')
                        self.status.set('Каталог не знайдено. Вставте посилання вручну.')
                elif action == 'vin':
                    self._clear_previous_catalogue()
                    self.candidate_panel.pack_forget()
                    self.candidate_box['values'] = ()
                    self.workflow_hint.set('Перевірте характеристики, збережіть авто, знайдіть каталог.')
                    self.vin_candidate = payload
                    _, data, provider = payload
                    self.brand.set(data['Make'])
                    self.model.set(data['Model'])
                    year = str(data.get('ModelYear', ''))
                    self.year.set(year if year.isdigit() and not data.get('ErrorCode', '').startswith(('5', '6', '7')) else '')
                    self.generation.set('')
                    self.catalogue.set('')
                    label = 'CarPot' if provider == 'carpot_vin' else 'NHTSA vPIC'
                    self.status.set(f'Джерело: {label}. Перевірте поля й натисніть «Зберегти авто».')
                elif action == 'imported':
                    self._load_last_job()
                    self._load_vehicles()
                    self.status.set(f'Додано записів: {payload}')
                elif action == 'error':
                    self.status.set('Помилка: ' + payload)
                    self._log('ПОМИЛКА: ' + payload)
                elif action == 'status':
                    self.status.set(payload)
                elif action == 'log':
                    self._log(payload)
                elif action == 'job':
                    self.job_id = payload
                elif action == 'stats':
                    self._show_stats(payload)
                elif action == 'refresh':
                    self._refresh()
                elif action == 'export':
                    files, valid, invalid = payload
                    self.export_files = files
                    self.status.set(f'Готово: {valid} записів у {len(files)} CSV. Потребують категорій: {invalid}.')
                    self._log('CSV: ' + '; '.join(str(f) for f in files))
                    if invalid:
                        self._log(f'{invalid} записів без категорій збережено окремо у JSON, до імпорту не включено.')
                    messagebox.showinfo('CarPot', f'Готово: {valid} записів у {len(files)} CSV.\n'
                                        f'Потребують уточнення категорії: {invalid}.\n\n'
                                        'Натисни «Відкрити імпорт у CarPot» та вибери CSV.')
        except queue.Empty:
            pass
        self.root.after(200, self._poll)


def main():
    if SEED_DB.is_file():
        local_store.install_seed(SEED_DB, DB_PATH)
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        error_file = DATA_DIR / 'fatal-error.log'
        error_file.write_text(traceback.format_exc(), encoding='utf-8')
        messagebox.showerror(APP_NAME, 'Програма не запустилася. Подробиці: ' + str(error_file))
