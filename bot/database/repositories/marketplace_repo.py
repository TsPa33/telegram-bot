from bot.database.base import fetch, fetchrow


async def list_marketplace_cars(
    query: str | None = None,
    city: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    verified: bool | None = None,
    limit: int = 12,
):
    search = f"%{query.strip()}%" if query else None
    city_filter = f"%{city.strip()}%" if city else None
    brand_filter = f"%{brand.strip()}%" if brand else None
    model_filter = f"%{model.strip()}%" if model else None

    return await fetch(
        """
        SELECT
            sc.id,
            sc.photo_id,
            sc.description,
            sc.views,
            sc.phone_clicks,
            sc.site_clicks,
            sc.seller_id,
            m.name AS model,
            b.name AS brand,
            s.username,
            s.telegram_id,
            s.phone,
            s.name,
            s.city,
            s.shop_name,
            s.website,
            s.is_verified
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        JOIN brands b ON m.brand_id = b.id
        WHERE sc.status = 'active'
          AND ($1::text IS NULL OR b.name ILIKE $1 OR m.name ILIKE $1 OR sc.description ILIKE $1 OR s.city ILIKE $1 OR s.shop_name ILIKE $1)
          AND ($2::text IS NULL OR s.city ILIKE $2)
          AND ($3::text IS NULL OR b.name ILIKE $3)
          AND ($4::text IS NULL OR m.name ILIKE $4)
          AND ($5::boolean IS NULL OR s.is_verified = $5)
        ORDER BY s.is_verified DESC, sc.id DESC
        LIMIT $6
        """,
        search,
        city_filter,
        brand_filter,
        model_filter,
        verified,
        limit,
    )


async def list_marketplace_services(
    query: str | None = None,
    city: str | None = None,
    category: str | None = None,
    verified: bool | None = None,
    urgent: bool | None = None,
    limit: int = 12,
):
    search = f"%{query.strip()}%" if query else None
    city_filter = f"%{city.strip()}%" if city else None
    category_filter = f"%{category.strip()}%" if category else None
    urgent_search = "%евакуатор%" if urgent else None

    return await fetch(
        """
        SELECT
            sv.id,
            sv.seller_id,
            sv.category,
            sv.title,
            sv.city,
            sv.address,
            sv.description,
            sv.website,
            sv.photo_id,
            sv.price,
            sv.created_at,
            COALESCE(st.views, 0) AS views,
            COALESCE(st.calls, 0) AS calls,
            COALESCE(st.clicks, 0) AS clicks,
            s.shop_name,
            s.name AS seller_name,
            s.username,
            s.phone,
            s.is_verified
        FROM services sv
        LEFT JOIN sellers s ON s.id = sv.seller_id
        LEFT JOIN service_stats st ON st.service_id = sv.id
        WHERE ($1::text IS NULL OR sv.title ILIKE $1 OR sv.category ILIKE $1 OR sv.description ILIKE $1 OR sv.city ILIKE $1 OR s.shop_name ILIKE $1)
          AND ($2::text IS NULL OR sv.city ILIKE $2)
          AND ($3::text IS NULL OR sv.category ILIKE $3)
          AND ($4::boolean IS NULL OR s.is_verified = $4)
          AND ($5::text IS NULL OR sv.title ILIKE $5 OR sv.category ILIKE $5 OR sv.description ILIKE $5)
        ORDER BY s.is_verified DESC NULLS LAST, sv.id DESC
        LIMIT $6
        """,
        search,
        city_filter,
        category_filter,
        verified,
        urgent_search,
        limit,
    )


async def list_featured_sellers(query: str | None = None, city: str | None = None, limit: int = 8):
    search = f"%{query.strip()}%" if query else None
    city_filter = f"%{city.strip()}%" if city else None

    return await fetch(
        """
        SELECT
            s.id,
            s.shop_name,
            s.name,
            s.username,
            s.phone,
            s.city,
            s.website,
            s.is_verified,
            ss.subdomain,
            COUNT(DISTINCT sc.id) FILTER (WHERE sc.status = 'active') AS cars_count,
            COUNT(DISTINCT sv.id) AS services_count
        FROM sellers s
        LEFT JOIN seller_sites ss ON ss.seller_id = s.id AND ss.status = 'active'
        LEFT JOIN seller_cars sc ON sc.seller_id = s.id
        LEFT JOIN services sv ON sv.seller_id = s.id
        WHERE ($1::text IS NULL OR s.shop_name ILIKE $1 OR s.name ILIKE $1 OR s.city ILIKE $1)
          AND ($2::text IS NULL OR s.city ILIKE $2)
        GROUP BY s.id, ss.subdomain
        HAVING COUNT(DISTINCT sc.id) FILTER (WHERE sc.status = 'active') > 0 OR COUNT(DISTINCT sv.id) > 0 OR ss.subdomain IS NOT NULL
        ORDER BY s.is_verified DESC, (COUNT(DISTINCT sc.id) + COUNT(DISTINCT sv.id)) DESC, s.id DESC
        LIMIT $3
        """,
        search,
        city_filter,
        limit,
    )


async def marketplace_summary():
    return await fetchrow(
        """
        SELECT
            (SELECT COUNT(*) FROM seller_cars WHERE status = 'active') AS cars_count,
            (SELECT COUNT(*) FROM services) AS services_count,
            (SELECT COUNT(*) FROM sellers) AS sellers_count,
            (SELECT COUNT(*) FROM seller_sites WHERE status = 'active') AS sites_count
        """
    )
