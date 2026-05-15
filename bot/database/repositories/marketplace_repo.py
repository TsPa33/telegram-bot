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
) -> dict:
    normalized_type = item_type if item_type in {"all", "cars", "services"} else "all"
    normalized_query = (q or "").strip()
    normalized_city = (city or "").strip()
    query_pattern = f"%{normalized_query}%" if normalized_query else None
    city_pattern = f"%{normalized_city}%" if normalized_city else None

    cars = []
    services = []
    sellers = []

    if normalized_type in {"all", "cars"}:
        cars = await fetch(
            """
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
            ORDER BY sc.id DESC
            LIMIT $3 OFFSET $4
            """,
            query_pattern,
            city_pattern,
            _safe_limit(limit),
            _safe_offset(offset),
        )

    if normalized_type in {"all", "services"}:
        services = await fetch(
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
            ORDER BY srv.id DESC
            LIMIT $3 OFFSET $4
            """,
            query_pattern,
            city_pattern,
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
            GROUP BY sel.id
            HAVING COUNT(DISTINCT sc.id) > 0 OR COUNT(DISTINCT srv.id) > 0 OR sel.is_verified = TRUE
            ORDER BY sel.is_verified DESC, sel.id DESC
            LIMIT $3 OFFSET $4
            """,
            query_pattern,
            city_pattern,
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
    }
