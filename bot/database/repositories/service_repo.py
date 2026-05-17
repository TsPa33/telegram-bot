from bot.database.base import execute, fetch, fetchrow
from bot.domain.statuses import get_service_display_status


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


async def _get_service_status_column() -> str | None:
    row = await fetchrow(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'services'
          AND column_name IN ('is_active', 'status')
        ORDER BY CASE column_name WHEN 'is_active' THEN 1 ELSE 2 END
        LIMIT 1
        """
    )
    return row["column_name"] if row else None


def _clean_text(value: str | None, max_length: int | None = None) -> str:
    cleaned = (value or "").strip()
    if max_length is not None:
        cleaned = cleaned[:max_length]
    return cleaned


def _normalize_price(price) -> int | None:
    if price in (None, ""):
        return None
    try:
        normalized = int(price)
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 0 else None


def _is_service_active(row) -> bool:
    if not row:
        return False
    if "is_active" in row.keys():
        return get_service_display_status(row["is_active"])["is_active"]
    if "status" in row.keys():
        return get_service_display_status(row["status"])["is_active"]
    return True


async def create_seller_service(
    *,
    seller_id: int,
    title: str,
    category: str,
    description: str = "",
    price=None,
    city: str = "",
    address: str = "",
    website: str = "",
):
    title = _clean_text(title, 160)
    category = _clean_text(category, 80) or "Інше"
    description = _clean_text(description, 2000)
    city = _clean_text(city, 120)
    address = _clean_text(address, 180)
    website = _clean_text(website, 240)
    normalized_price = _normalize_price(price)

    if not title:
        return None

    row = await fetchrow(
        """
        INSERT INTO services (
            seller_id, category, title, city, address, description, website, photo_id, price
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, NULL, $8)
        RETURNING id
        """,
        seller_id,
        category,
        title,
        city,
        address,
        description or None,
        website or None,
        normalized_price,
    )
    if not row:
        return None

    service_id = row["id"]
    await execute(
        """
        INSERT INTO service_stats (service_id, views, calls, clicks)
        VALUES ($1, 0, 0, 0)
        ON CONFLICT (service_id) DO NOTHING
        """,
        service_id,
    )
    return service_id


async def update_seller_service(
    *,
    seller_id: int,
    service_id: int,
    title: str,
    category: str,
    description: str = "",
    price=None,
):
    title = _clean_text(title, 160)
    category = _clean_text(category, 80) or "Інше"
    description = _clean_text(description, 2000)
    normalized_price = _normalize_price(price)

    if not title:
        return None

    row = await fetchrow(
        """
        UPDATE services
        SET title = $1,
            category = $2,
            description = $3,
            price = $4
        WHERE id = $5
          AND seller_id = $6
        RETURNING id
        """,
        title,
        category,
        description or None,
        normalized_price,
        service_id,
        seller_id,
    )
    return row is not None


async def get_seller_service_detail(*, seller_id: int, service_id: int):
    status_column = await _get_service_status_column()
    status_select = f", sv.{status_column}" if status_column else ""
    row = await fetchrow(
        f"""
        SELECT
            sv.id AS service_id,
            sv.id,
            sv.seller_id,
            sv.title,
            sv.title AS name,
            sv.category,
            sv.description,
            sv.price,
            sv.city,
            sv.address,
            sv.website,
            sv.photo_id,
            COALESCE(st.views, 0)::int AS views,
            COALESCE(st.calls, 0)::int AS calls,
            COALESCE(st.clicks, 0)::int AS clicks,
            sv.created_at,
            (COALESCE(NULLIF(BTRIM(sv.description), ''), '') <> '') AS has_description,
            (sv.price IS NOT NULL) AS has_price,
            (COALESCE(NULLIF(sv.photo_id, ''), '') <> '') AS has_photo
            {status_select}
        FROM services sv
        LEFT JOIN service_stats st ON st.service_id = sv.id
        WHERE sv.id = $1
          AND sv.seller_id = $2
        LIMIT 1
        """,
        service_id,
        seller_id,
    )
    if not row:
        return None

    service = dict(row)
    service["status_supported"] = bool(status_column)
    service["status_field"] = status_column
    service["is_active"] = _is_service_active(row)
    completed = sum(1 for key in ("title", "category") if service.get(key))
    completed += 1 if service.get("has_description") else 0
    completed += 1 if service.get("has_price") else 0
    completed += 1 if service.get("has_photo") else 0
    service["content_completeness"] = round((completed / 5) * 100)
    return service


async def toggle_seller_service_status(*, seller_id: int, service_id: int, is_active: bool) -> bool:
    status_column = await _get_service_status_column()
    if not status_column:
        return False

    if status_column == "is_active":
        row = await fetchrow(
            """
            UPDATE services
            SET is_active = $1
            WHERE id = $2
              AND seller_id = $3
            RETURNING id
            """,
            is_active,
            service_id,
            seller_id,
        )
    else:
        row = await fetchrow(
            """
            UPDATE services
            SET status = $1
            WHERE id = $2
              AND seller_id = $3
            RETURNING id
            """,
            "active" if is_active else "inactive",
            service_id,
            seller_id,
        )
    return row is not None
