import asyncio
import time
from typing import Any, Dict, Tuple, Optional


# ================= CONFIG =================

CACHE_TTL = 300  # 5 хвилин


# ================= STORAGE =================

brands_cache: Optional[Tuple[float, Any]] = None
models_cache: Dict[str, Tuple[float, Any]] = {}

brands_lock = asyncio.Lock()
models_lock = asyncio.Lock()


# ================= BRANDS =================

async def get_cached_brands(fetch_func):
    global brands_cache

    async with brands_lock:
        if brands_cache:
            ts, data = brands_cache

            if time.time() - ts < CACHE_TTL:
                return data

        data = await fetch_func()
        brands_cache = (time.time(), data)

        return data


def clear_brands_cache():
    global brands_cache
    brands_cache = None


# ================= MODELS =================

async def get_cached_models(brand: str, fetch_func):
    global models_cache

    key = brand.lower()

    async with models_lock:
        if key in models_cache:
            ts, data = models_cache[key]

            if time.time() - ts < CACHE_TTL:
                return data

        data = await fetch_func(brand)
        models_cache[key] = (time.time(), data)

        return data


def clear_models_cache(brand: Optional[str] = None):
    global models_cache

    if brand:
        models_cache.pop(brand.lower(), None)
    else:
        models_cache = {}
