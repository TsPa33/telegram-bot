"""Universal EN->UK automotive name translation, independent of make/model.

Translation is optional and runs only with an explicit DeepL API key.
No VIN, parts IDs, supplier secrets or customer data leave the backend.
The same normalized source phrase is reused for every make and model.
"""
import os
import re
from collections import OrderedDict
from threading import RLock
from time import monotonic

import httpx

_CACHE_TTL = 86400 * 7
_CACHE_LIMIT = 5000
_cache = OrderedDict()
_lock = RLock()
_UK_LETTERS = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")


class TranslationError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def translate_names(names: list[str], *, transport=None) -> dict:
    """Translate arbitrary English part type labels in batches, returning status per item.

    Missing configuration is surfaced as such, never represented as a completed translation.
    DeepL preserves input order. On failure no guessed/partial provider text is accepted.
    """
    if len(names) > 400:
        raise TranslationError(422, "Максимум 400 назв за один аналіз")
    original = [str(s).strip() for s in names]
    if any(not x or len(x) > 240 for x in original):
        raise TranslationError(422, "Назва повинна містити від 1 до 240 символів")
    unique = list(dict.fromkeys(original))
    api_key = os.getenv("WAREHOUSE_DEEPL_API_KEY", "").strip()
    now = monotonic()
    results = {}
    with _lock:
        for name in unique:
            cached = _cache.get(name.casefold())
            if cached and cached[0] > now:
                results[name] = cached[1]
                _cache.move_to_end(name.casefold())
        pending = [x for x in unique if x not in results and not _UK_LETTERS.search(x)]
        for name in unique:
            if name not in results and _UK_LETTERS.search(name):
                results[name] = name
        if pending and not api_key:
            return {"configured": False, "translations": results, "untranslated": pending}
        endpoint = "https://api-free.deepl.com/v2/translate" if api_key.endswith(":fx") else "https://api.deepl.com/v2/translate"
        if pending:
            try:
                with httpx.Client(timeout=httpx.Timeout(20, connect=5), transport=transport) as client:
                    for start in range(0, len(pending), 40):
                        chunk = pending[start:start+40]
                        response = client.post(
                            endpoint,
                            headers={"Authorization": "DeepL-Auth-Key " + api_key,
                                     "Content-Type": "application/json"},
                            json={"text": chunk, "source_lang": "EN", "target_lang": "UK",
                                  "context": "Automotive spare parts catalogue. Translate technical auto-parts names accurately into Ukrainian. Preserve distinctions between components, kits, consumables, and tools."},
                        )
                        if response.status_code == 429:
                            raise TranslationError(429, "Сервіс перекладу обмежив частоту запитів")
                        if response.status_code in (403, 456):
                            raise TranslationError(503, "Ключ або баланс сервісу перекладу недоступні")
                        if response.status_code != 200:
                            raise TranslationError(502, "Сервіс перекладу тимчасово недоступний")
                        rows = response.json().get("translations", [])
                        if not isinstance(rows, list) or len(rows) != len(chunk):
                            raise TranslationError(502, "Некоректна відповідь сервісу перекладу")
                        for original_name, row in zip(chunk, rows):
                            translation = row.get("text") if isinstance(row, dict) else None
                            if not isinstance(translation, str) or not translation.strip():
                                raise TranslationError(502, "Перекладач повернув порожню назву")
                            localized = translation.strip()
                            results[original_name] = localized
                            _cache[original_name.casefold()] = (monotonic() + _CACHE_TTL, localized)
                            _cache.move_to_end(original_name.casefold())
                            while len(_cache) > _CACHE_LIMIT:
                                _cache.popitem(last=False)
            except httpx.HTTPError:
                raise TranslationError(502, "Не вдалося підключитися до перекладача") from None
    return {"configured": bool(api_key), "translations": results, "untranslated": []}
