from bot.database.base import fetch, fetchrow


async def list_crm_sellers(
    query: str | None = None,
    verified: str | None = None,
    has_site: str | None = None,
    limit: int = 100,
):
    filters = []
    args = []

    if query:
        args.append(f"%{query.strip()}%")
        param = f"${len(args)}"
        filters.append(
            f"""
            (
                s.telegram_id::text ILIKE {param}
                OR s.username ILIKE {param}
                OR s.phone ILIKE {param}
                OR s.shop_name ILIKE {param}
                OR s.name ILIKE {param}
            )
            """
        )

    if verified == "yes":
        filters.append("COALESCE(s.is_verified, FALSE) = TRUE")
    elif verified == "no":
        filters.append("COALESCE(s.is_verified, FALSE) = FALSE")

    if has_site == "yes":
        filters.append("site.id IS NOT NULL")
    elif has_site == "no":
        filters.append("site.id IS NULL")

    args.append(limit)
    limit_param = f"${len(args)}"
    where_sql = ""

    if filters:
        where_sql = "WHERE " + " AND ".join(filters)

    return await fetch(
        f"""
        SELECT
            s.id,
            s.telegram_id,
            s.username,
            s.phone,
            s.shop_name,
            s.name,
            s.website,
            s.city,
            s.is_verified,
            s.created_at,
            site.id AS site_id,
            site.subdomain AS site_subdomain,
            site.status AS site_status,
            (site.id IS NOT NULL) AS has_site
        FROM sellers s
        LEFT JOIN seller_sites site ON site.seller_id = s.id
        {where_sql}
        ORDER BY s.created_at DESC, s.id DESC
        LIMIT {limit_param}
        """,
        *args,
    )


async def get_crm_seller_detail(seller_id: int):
    return await fetchrow(
        """
        SELECT
            s.id,
            s.telegram_id,
            s.username,
            s.phone,
            s.shop_name,
            s.name,
            s.website,
            s.city,
            s.is_verified,
            s.description,
            s.photo_id,
            s.created_at,
            s.cars_limit,
            s.cars_used,
            site.id AS site_id,
            site.subdomain AS site_subdomain,
            site.status AS site_status,
            (site.id IS NOT NULL) AS has_site
        FROM sellers s
        LEFT JOIN seller_sites site ON site.seller_id = s.id
        WHERE s.id = $1
        LIMIT 1
        """,
        seller_id,
    )


async def get_crm_seller_cars(seller_id: int):
    return await fetch(
        """
        SELECT
            sc.id,
            sc.seller_id,
            sc.photo_id,
            sc.description,
            sc.status,
            sc.views,
            sc.phone_clicks,
            sc.site_clicks,
            sc.created_at,
            m.name AS model,
            b.name AS brand
        FROM seller_cars sc
        LEFT JOIN models m ON m.id = sc.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        WHERE sc.seller_id = $1
        ORDER BY sc.created_at DESC, sc.id DESC
        """,
        seller_id,
    )


async def get_crm_seller_services(seller_id: int):
    return await fetch(
        """
        SELECT
            s.id,
            s.seller_id,
            s.category,
            s.title,
            s.city,
            s.address,
            s.description,
            s.website,
            s.photo_id,
            s.price,
            s.created_at,
            COALESCE(st.views, 0) AS views,
            COALESCE(st.calls, 0) AS calls,
            COALESCE(st.clicks, 0) AS clicks
        FROM services s
        LEFT JOIN service_stats st ON st.service_id = s.id
        WHERE s.seller_id = $1
        ORDER BY s.created_at DESC, s.id DESC
        """,
        seller_id,
    )


async def get_crm_seller_site(seller_id: int):
    return await fetchrow(
        """
        SELECT
            id,
            seller_id,
            subdomain,
            status,
            has_custom_domain,
            custom_domain,
            created_at,
            updated_at
        FROM seller_sites
        WHERE seller_id = $1
        LIMIT 1
        """,
        seller_id,
    )


async def get_crm_seller_subscriptions(seller_id: int):
    return await fetch(
        """
        SELECT
            ss.id,
            ss.seller_id,
            ss.slots,
            ss.created_at,
            ss.expires_at,
            ss.payment_id,
            p.order_id AS payment_order_id,
            p.amount AS payment_amount,
            p.status AS payment_status,
            p.product AS payment_product
        FROM seller_subscriptions ss
        LEFT JOIN payments p ON p.id = ss.payment_id
        WHERE ss.seller_id = $1
        ORDER BY ss.created_at DESC, ss.id DESC
        """,
        seller_id,
    )
