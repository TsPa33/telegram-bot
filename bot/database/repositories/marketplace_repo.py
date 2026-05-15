from bot.database.base import fetch, fetchrow


DEFAULT_LIMIT = 12
MAX_LIMIT = 48


def _safe_limit(limit: int) -> int:
    return max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))


def _safe_offset(offset: int) -> int:
    return max(0, int(offset or 0))


async def get_marketplace_summary() -> dict:
    """Return public marketplace counters for isolated buyer pages."""
    row = await fetchrow(
        """
        SELECT
            (SELECT COUNT(*)::int FROM seller_cars sc WHERE sc.status::text IN ('active', '1')) AS cars_count,
            (SELECT COUNT(*)::int FROM services) AS services_count,
            (SELECT COUNT(*)::int FROM sellers) AS sellers_count,
            (
                SELECT COUNT(DISTINCT city)::int
                FROM (
                    SELECT city FROM sellers WHERE city IS NOT NULL AND trim(city) <> ''
                    UNION
                    SELECT city FROM services WHERE city IS NOT NULL AND trim(city) <> ''
                ) cities
            ) AS cities_count
        """
    )

    if not row:
        return {
            "cars_count": 0,
            "services_count": 0,
            "sellers_count": 0,
            "cities_count": 0,
        }

    return dict(row)


async def get_latest_cars(limit: int = DEFAULT_LIMIT, offset: int = 0):
    return await fetch(
        """
        SELECT
            sc.id,
            sc.seller_id,
            sc.photo_id,
            sc.description,
            sc.views,
            sc.phone_clicks,
            sc.site_clicks,
            sc.created_at,
            m.name AS model,
            b.name AS brand,
            sel.username,
            sel.telegram_id,
            sel.phone,
            sel.name,
            sel.city,
            sel.shop_name,
            sel.website,
            sel.is_verified
        FROM seller_cars sc
        JOIN sellers sel ON sel.id = sc.seller_id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.status::text IN ('active', '1')
        ORDER BY sc.id DESC
        LIMIT $1 OFFSET $2
        """,
        _safe_limit(limit),
        _safe_offset(offset),
    )


async def get_latest_services(limit: int = DEFAULT_LIMIT, offset: int = 0):
    return await fetch(
        """
        SELECT
            srv.id,
            srv.seller_id,
            srv.category,
            srv.title,
            srv.city,
            srv.address,
            srv.description,
            srv.website,
            srv.photo_id,
            srv.price,
            srv.created_at,
            sel.username,
            sel.telegram_id,
            sel.phone,
            sel.name,
            sel.shop_name,
            sel.is_verified,
            COALESCE(st.views, 0) AS views,
            COALESCE(st.calls, 0) AS calls,
            COALESCE(st.clicks, 0) AS clicks
        FROM services srv
        LEFT JOIN sellers sel ON sel.id = srv.seller_id
        LEFT JOIN service_stats st ON st.service_id = srv.id
        ORDER BY srv.id DESC
        LIMIT $1 OFFSET $2
        """,
        _safe_limit(limit),
        _safe_offset(offset),
    )


async def get_featured_sellers(limit: int = 8, offset: int = 0):
    return await fetch(
        """
        SELECT
            sel.id,
            sel.telegram_id,
            sel.username,
            sel.phone,
            sel.name,
            sel.city,
            sel.shop_name,
            sel.website,
            sel.is_verified,
            sel.description,
            sel.photo_id,
            COUNT(DISTINCT sc.id)::int AS cars_count,
            COUNT(DISTINCT srv.id)::int AS services_count
        FROM sellers sel
        LEFT JOIN seller_cars sc
            ON sc.seller_id = sel.id
           AND sc.status::text IN ('active', '1')
        LEFT JOIN services srv ON srv.seller_id = sel.id
        GROUP BY sel.id
        HAVING COUNT(DISTINCT sc.id) > 0 OR COUNT(DISTINCT srv.id) > 0 OR sel.is_verified = TRUE
        ORDER BY sel.is_verified DESC, (COUNT(DISTINCT sc.id) + COUNT(DISTINCT srv.id)) DESC, sel.id DESC
        LIMIT $1 OFFSET $2
        """,
        _safe_limit(limit),
        _safe_offset(offset),
    )


async def search_marketplace(
    q: str | None = None,
    city: str | None = None,
    item_type: str = "all",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    category: str | None = None,
    service_type: str | None = None,
    brand: str | None = None,
    condition: str | None = None,
    verified: str | None = None,
    sort: str | None = "new",
) -> dict:
    normalized_type = item_type if item_type in {"all", "cars", "services"} else "all"
    normalized_query = (q or "").strip()
    normalized_city = (city or "").strip()
    normalized_category = (category or "").strip()
    normalized_service_type = (service_type or "").strip()
    normalized_brand = (brand or "").strip()
    normalized_condition = (condition or "").strip()
    normalized_verified = "true" if str(verified or "").lower() == "true" else ""
    normalized_sort = sort if sort in {"new", "popular", "trusted"} else "new"

    query_pattern = f"%{normalized_query}%" if normalized_query else None
    city_pattern = f"%{normalized_city}%" if normalized_city else None
    category_pattern = f"%{normalized_category}%" if normalized_category else None
    service_type_pattern = f"%{normalized_service_type}%" if normalized_service_type else None
    brand_pattern = f"%{normalized_brand}%" if normalized_brand else None
    condition_pattern = f"%{normalized_condition}%" if normalized_condition else None
    verified_filter = True if normalized_verified == "true" else None

    car_category_allows = not normalized_category or any(
        marker in normalized_category.lower()
        for marker in ("авто", "зап", "дет", "car", "part")
    )

    car_order = {
        "new": "sc.id DESC",
        "popular": "COALESCE(sc.views, 0) DESC, sc.id DESC",
        "trusted": "sel.is_verified DESC, sc.id DESC",
    }[normalized_sort]
    service_order = {
        "new": "srv.id DESC",
        "popular": "COALESCE(st.views, 0) DESC, srv.id DESC",
        "trusted": "sel.is_verified DESC, srv.id DESC",
    }[normalized_sort]

    cars = []
    services = []
    sellers = []

    if normalized_type in {"all", "cars"} and car_category_allows:
        cars = await fetch(
            f"""
            SELECT
                sc.id,
                sc.seller_id,
                sc.photo_id,
                sc.description,
                sc.views,
                sc.created_at,
                m.name AS model,
                b.name AS brand,
                sel.username,
                sel.telegram_id,
                sel.phone,
                sel.name,
                sel.city,
                sel.shop_name,
                sel.website,
                sel.is_verified
            FROM seller_cars sc
            JOIN sellers sel ON sel.id = sc.seller_id
            JOIN models m ON m.id = sc.model_id
            JOIN brands b ON b.id = m.brand_id
            WHERE sc.status::text IN ('active', '1')
              AND ($1::text IS NULL OR b.name ILIKE $1 OR m.name ILIKE $1 OR sc.description ILIKE $1 OR sel.shop_name ILIKE $1 OR sel.name ILIKE $1)
              AND ($2::text IS NULL OR sel.city ILIKE $2)
              AND ($3::text IS NULL OR b.name ILIKE $3)
              AND ($4::text IS NULL OR sc.description ILIKE $4)
              AND ($5::boolean IS NULL OR sel.is_verified = $5)
            ORDER BY {car_order}
            LIMIT $6 OFFSET $7
            """,
            query_pattern,
            city_pattern,
            brand_pattern,
            condition_pattern,
            verified_filter,
            _safe_limit(limit),
            _safe_offset(offset),
        )

    if normalized_type in {"all", "services"}:
        services = await fetch(
            f"""
            SELECT
                srv.id,
                srv.seller_id,
                srv.category,
                srv.title,
                srv.city,
                srv.address,
                srv.description,
                srv.website,
                srv.price,
                srv.created_at,
                sel.username,
                sel.telegram_id,
                sel.phone,
                sel.name,
                sel.shop_name,
                sel.is_verified,
                COALESCE(st.views, 0) AS views
            FROM services srv
            LEFT JOIN sellers sel ON sel.id = srv.seller_id
            LEFT JOIN service_stats st ON st.service_id = srv.id
            WHERE ($1::text IS NULL OR srv.category ILIKE $1 OR srv.title ILIKE $1 OR srv.description ILIKE $1 OR sel.shop_name ILIKE $1 OR sel.name ILIKE $1)
              AND ($2::text IS NULL OR srv.city ILIKE $2 OR sel.city ILIKE $2)
              AND ($3::text IS NULL OR srv.category ILIKE $3 OR srv.title ILIKE $3)
              AND ($4::text IS NULL OR srv.category ILIKE $4 OR srv.title ILIKE $4 OR srv.description ILIKE $4)
              AND ($5::boolean IS NULL OR sel.is_verified = $5)
            ORDER BY {service_order}
            LIMIT $6 OFFSET $7
            """,
            query_pattern,
            city_pattern,
            category_pattern,
            service_type_pattern,
            verified_filter,
            _safe_limit(limit),
            _safe_offset(offset),
        )

    if normalized_type == "all":
        sellers = await fetch(
            """
            SELECT
                sel.id,
                sel.telegram_id,
                sel.username,
                sel.phone,
                sel.name,
                sel.city,
                sel.shop_name,
                sel.website,
                sel.is_verified,
                sel.description,
                COUNT(DISTINCT sc.id)::int AS cars_count,
                COUNT(DISTINCT srv.id)::int AS services_count
            FROM sellers sel
            LEFT JOIN seller_cars sc
                ON sc.seller_id = sel.id
               AND sc.status::text IN ('active', '1')
            LEFT JOIN services srv ON srv.seller_id = sel.id
            WHERE ($1::text IS NULL OR sel.shop_name ILIKE $1 OR sel.name ILIKE $1 OR sel.description ILIKE $1)
              AND ($2::text IS NULL OR sel.city ILIKE $2)
              AND ($3::boolean IS NULL OR sel.is_verified = $3)
            GROUP BY sel.id
            HAVING COUNT(DISTINCT sc.id) > 0 OR COUNT(DISTINCT srv.id) > 0 OR sel.is_verified = TRUE
            ORDER BY sel.is_verified DESC, sel.id DESC
            LIMIT $4 OFFSET $5
            """,
            query_pattern,
            city_pattern,
            verified_filter,
            8,
            0,
        )

    return {
        "cars": cars,
        "services": services,
        "sellers": sellers,
        "query": normalized_query,
        "city": normalized_city,
        "type": normalized_type,
        "category": normalized_category,
        "service_type": normalized_service_type,
        "brand": normalized_brand,
        "condition": normalized_condition,
        "verified": normalized_verified,
        "sort": normalized_sort,
    }
