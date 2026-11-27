"""Read-only vehicle catalogue client for the existing Warehouse staging API."""
from contextlib import closing
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
import re
import sqlite3
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

BASE = 'https://confident-sparkle-warehouse-staging.up.railway.app/api/v1'
MAX_RESPONSE = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CatalogueClient:
    def __init__(self, cache_path=None):
        self.cache_path = cache_path
        self.cookies = CookieJar()
        self.opener = build_opener(NoRedirect(), HTTPCookieProcessor(self.cookies))

    @property
    def connected(self):
        return any(cookie.name == 'warehouse_session' and not cookie.is_expired() for cookie in self.cookies)

    def _request(self, endpoint, *, params=None, data=None):
        url = BASE + endpoint
        if params:
            url += '?' + urlencode(params)
        body = json.dumps(data).encode() if data is not None else None
        headers = {'Accept': 'application/json', 'X-Warehouse-Client': '5'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with self.opener.open(Request(url, data=body, headers=headers), timeout=12) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except HTTPError as error:
            if error.code == 401:
                self.cookies.clear()
                raise ValueError('Сесія Warehouse недійсна. Увійдіть знову.') from None
            raise ValueError(f'Warehouse Staging відповів HTTP {error.code}') from None
        if len(raw) > MAX_RESPONSE:
            raise ValueError('Відповідь Warehouse перевищує ліміт')
        return json.loads(raw)

    def login(self, email, password):
        result = self._request('/auth/login', data={'email': email, 'password': password})
        if not self.connected or result.get('user', {}).get('must_change_password'):
            self.cookies.clear()
            raise ValueError('Завершіть вхід до Warehouse Staging у браузері')

    def decode(self, vin):
        data = self._request('/vehicles/vin/decode', params={'vin': vin})
        vehicle = data.get('vehicle') or {}
        if not vehicle.get('manufacturer') or not vehicle.get('model'):
            raise ValueError('CarPot не визначив марку або модель')
        return vehicle

    def _cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        database = sqlite3.connect(self.cache_path, timeout=5)
        database.execute("""CREATE TABLE IF NOT EXISTS directory_v1 (
                            cache_key TEXT PRIMARY KEY, updated_at TEXT, payload TEXT)""")
        return database

    def page(self, level, *, kind, parent=None, name='', after=0, offline=False):
        endpoints = {
            'make': ('source-manufacturer-directory', {'name': name}),
            'model': ('source-models', {'manufacturer_id': parent}),
            'modification': ('source-modifications', {'model_id': parent}),
        }
        endpoint, params = endpoints[level]
        params = {**params, 'kind': kind, 'after': after}
        key = endpoint + '?' + urlencode(params)
        updated_at = None
        if offline:
            if self.cache_path is None:
                raise ValueError('Кеш довідника недоступний')
            with closing(self._cache()) as db:
                saved = db.execute('SELECT updated_at,payload FROM directory_v1 WHERE cache_key=?', (key,)).fetchone()
            if not saved:
                raise ValueError('Ця сторінка ще не збережена в кеші')
            updated_at, raw = saved
            result = json.loads(raw)
        else:
            result = self._request('/vehicles/vin/' + endpoint, params=params)
        rows, cursor = result['items'], result.get('next_after')
        if not isinstance(rows, list) or len(rows) > 50:
            raise ValueError('Некоректна сторінка каталогу')
        if any(type(item.get('id')) is not int or item['id'] <= after or not isinstance(item.get('name'), str)
               for item in rows):
            raise ValueError('Некоректний запис каталогу')
        ids = [item['id'] for item in rows]
        if ids != sorted(set(ids)) or cursor is not None and (type(cursor) is not int or not ids or cursor != ids[-1]):
            raise ValueError('Некоректний курсор каталогу')
        if not offline and self.cache_path is not None:
            with closing(self._cache()) as db, db:
                db.execute('INSERT OR REPLACE INTO directory_v1 VALUES (?,?,?)',
                           (key, datetime.now(timezone.utc).isoformat(), json.dumps(result, ensure_ascii=False)))
        return rows, cursor, updated_at


def includes_year(interval, year):
    if year is None:
        return True
    edge = r'(?:(?:0?[1-9]|1[0-2])[./-])?((?:18|19|20)\d{2}|2100)(?:[./]?(?:0[1-9]|1[0-2]))?'
    match = re.fullmatch(fr'\s*(?:{edge})?\s*[-–—]\s*(?:{edge})?\s*', str(interval or ''))
    if not match or not any(match.groups()):
        return False
    start, end = (int(v) if v else None for v in match.groups())
    return (start is None or start <= year) and (end is None or year <= end)
