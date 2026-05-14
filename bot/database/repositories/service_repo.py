from bot.database.base import execute, fetch, fetchrow


ALLOWED_UPDATE_FIELDS = {
    "category",
    "title",
    "city",
    "address",
    "description",
    "website",
    "photo_id",
    "price",
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
            s.price,
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


# 🔥 ОСЬ ТУТ ГОЛОВНИЙ ФІКС
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
            s.price,
            s.created_at,
            sel.phone,
            COALESCE(st.views, 0) AS views,
            COALESCE(st.calls, 0) AS calls,
            COALESCE(st.clicks, 0) AS clicks
        FROM services s
        LEFT JOIN sellers sel ON sel.id = s.seller_id
        LEFT JOIN service_stats st ON st.service_id = s.id
        WHERE LOWER(s.city) = LOWER($1)
          AND LOWER(s.category) = LOWER($2)
        ORDER BY s.id DESC
        """,
        city,
        category,
    )


async def get_service_by_id(service_id: int):
    return await fetchrow(
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
            sel.phone,
            COALESCE(st.views, 0) AS views,
            COALESCE(st.calls, 0) AS calls,
            COALESCE(st.clicks, 0) AS clicks
        FROM services s
        LEFT JOIN sellers sel ON sel.id = s.seller_id
        LEFT JOIN service_stats st ON st.service_id = s.id
        WHERE s.id = $1
        LIMIT 1
        """,
        service_id,
    )


async def get_all_cities():
    return await fetch(
        """
        SELECT DISTINCT city
        FROM services
        WHERE city IS NOT NULL
        ORDER BY city
        """
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


async def update_service_field(service_id: int, field: str, value) -> bool:
    return await update_service(service_id, field, value)


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


async def get_service_by_id(service_id: int):
    return await fetchrow(
        """
        SELECT *
        FROM services
        WHERE id = $1
        LIMIT 1
        """,
        service_id,
    )


async def get_service_by_seller(service_id: int, seller_id: int):
    return await fetchrow(
        """
        SELECT *
        FROM services
        WHERE id = $1
          AND seller_id = $2
        LIMIT 1
        """,
        service_id,
        seller_id,
    )


async def update_service_photo(service_id: int, seller_id: int, image_url: str) -> bool:
    row = await fetchrow(
        """
        UPDATE services
        SET photo_id = $1
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        image_url,
        service_id,
        seller_id,
    )
    return row is not None


async def clear_service_photo(service_id: int, seller_id: int) -> bool:
    row = await fetchrow(
        """
        UPDATE services
        SET photo_id = NULL
        WHERE id = $1
          AND seller_id = $2
        RETURNING id
        """,
        service_id,
        seller_id,
    )
    return row is not None


async def delete_service_by_seller(service_id: int, seller_id: int) -> bool:
    row = await fetchrow(
        """
        DELETE FROM services
        WHERE id = $1
          AND seller_id = $2
        RETURNING id
        """,
        service_id,
        seller_id,
    )
    if not row:
        return False

    await execute("DELETE FROM service_stats WHERE service_id = $1", service_id)
    return True


async def delete_services_by_seller(seller_id: int) -> int:
    rows = await fetch(
        """
        DELETE FROM service_stats
        WHERE service_id IN (
            SELECT id FROM services WHERE seller_id = $1
        )
        RETURNING service_id
        """,
        seller_id,
    )

    deleted_services = await fetch(
        """
        DELETE FROM services
        WHERE seller_id = $1
        RETURNING id
        """,
        seller_id,
    )

    return len(deleted_services) if deleted_services else len(rows)


async def bulk_create_services(seller_id: int, services: list[dict]) -> list[int]:
    service_ids: list[int] = []

    for service in services:
        row = await fetchrow(
            """
            INSERT INTO services (
                seller_id,
                category,
                title,
                city,
                address,
                description,
                website,
                photo_id,
                price
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            seller_id,
            service.get("category"),
            service.get("title"),
            service.get("city"),
            service.get("address"),
            service.get("description"),
            service.get("website"),
            service.get("photo_id") or None,
            service.get("price"),
        )

        if not row:
            continue

        service_id = row["id"]
        service_ids.append(service_id)

        await execute(
            """
            INSERT INTO service_stats (service_id, views, calls, clicks)
            VALUES ($1, 0, 0, 0)
            ON CONFLICT (service_id) DO NOTHING
            """,
            service_id,
        )

    return service_ids
