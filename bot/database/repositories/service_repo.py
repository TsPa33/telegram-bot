from bot.database.base import execute, fetch


ALLOWED_UPDATE_FIELDS = {
    "category",
    "title",
    "city",
    "address",
    "description",
    "website",
    "photo_id",
}


async def create_service(
    seller_id: int,
    category: str,
    title: str,
    city: str,
    address: str,
    description: str | None,
    website: str | None,
    photo_id: str | None,
):
    rows = await fetch(
        """
        INSERT INTO services (
            seller_id,
            category,
            title,
            city,
            address,
            description,
            website,
            photo_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        seller_id,
        category,
        title,
        city,
        address,
        description,
        website,
        photo_id,
    )

    if not rows:
        return None

    service_id = rows[0]["id"]

    await execute(
        """
        INSERT INTO service_stats (service_id, views, calls, clicks)
        VALUES ($1, 0, 0, 0)
        ON CONFLICT (service_id) DO NOTHING
        """,
        service_id,
    )

    return service_id


async def get_services_by_seller(seller_id: int):
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
            s.created_at,
            COALESCE(st.views, 0) AS views,
            COALESCE(st.calls, 0) AS calls,
            COALESCE(st.clicks, 0) AS clicks
        FROM services s
        LEFT JOIN service_stats st ON st.service_id = s.id
        WHERE s.seller_id = $1
        ORDER BY s.id DESC
        """,
        seller_id,
    )


async def get_services_by_filter(city: str, category: str):
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
            s.created_at,
            sel.phone,
            COALESCE(st.views, 0) AS views,
            COALESCE(st.calls, 0) AS calls,
            COALESCE(st.clicks, 0) AS clicks
        FROM services s
        LEFT JOIN sellers sel ON sel.id = s.seller_id
        LEFT JOIN service_stats st ON st.service_id = s.id
        WHERE s.city = $1
          AND s.category = $2
        ORDER BY s.id DESC
        """,
        city,
        category,
    )


async def delete_service(service_id: int):
    await execute("DELETE FROM service_stats WHERE service_id = $1", service_id)
    await execute("DELETE FROM services WHERE id = $1", service_id)


async def update_service(service_id: int, field: str, value):
    if field not in ALLOWED_UPDATE_FIELDS:
        return False

    rows = await fetch(
        f"""
        UPDATE services
        SET {field} = $1
        WHERE id = $2
        RETURNING id
        """,
        value,
        service_id,
    )

    return bool(rows)


async def increment_views(service_id: int):
    await execute(
        """
        INSERT INTO service_stats (service_id, views, calls, clicks)
        VALUES ($1, 1, 0, 0)
        ON CONFLICT (service_id)
        DO UPDATE SET views = service_stats.views + 1
        """,
        service_id,
    )


async def increment_calls(service_id: int):
    await execute(
        """
        INSERT INTO service_stats (service_id, views, calls, clicks)
        VALUES ($1, 0, 1, 0)
        ON CONFLICT (service_id)
        DO UPDATE SET calls = service_stats.calls + 1
        """,
        service_id,
    )


async def increment_clicks(service_id: int):
    await execute(
        """
        INSERT INTO service_stats (service_id, views, calls, clicks)
        VALUES ($1, 0, 0, 1)
        ON CONFLICT (service_id)
        DO UPDATE SET clicks = service_stats.clicks + 1
        """,
        service_id,
    )


async def get_service_stats(service_id: int):
    rows = await fetch(
        """
        SELECT
            service_id,
            COALESCE(views, 0) AS views,
            COALESCE(calls, 0) AS calls,
            COALESCE(clicks, 0) AS clicks
        FROM service_stats
        WHERE service_id = $1
        """,
        service_id,
    )

    if rows:
        return rows[0]

    return {"service_id": service_id, "views": 0, "calls": 0, "clicks": 0}
