brands_cache = None
models_cache = {}


# ================= BRANDS =================

async def get_cached_brands(fetch_func):
    global brands_cache

    if brands_cache is None:
        brands_cache = await fetch_func()

    return brands_cache


def clear_brands_cache():
    global brands_cache
    brands_cache = None


# ================= MODELS =================

async def get_cached_models(brand: str, fetch_func):
    global models_cache

    key = brand.lower()

    if key not in models_cache:
        models_cache[key] = await fetch_func(brand)

    return models_cache[key]


def clear_models_cache(brand: str | None = None):
    global models_cache

    if brand:
        models_cache.pop(brand.lower(), None)
    else:
        models_cache = {}
