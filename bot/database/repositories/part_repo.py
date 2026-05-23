from decimal import Decimal

from bot.database.base import fetch, fetchrow

VALID_PART_STATUSES = {"draft", "available", "sold", "hidden"}


async def get_active_part_templates(vehicle_type: str = "passenger"):
    return await fetch(
        """
        SELECT id, vehicle_type, category, name, sort_order
        FROM part_templates
        WHERE vehicle_type = $1
          AND is_active = TRUE
        ORDER BY category, sort_order, name
        """,
        vehicle_type,
    )


async def generate_parts_for_car(
    seller_id: int,
    car_id: int,
    vehicle_type: str = "passenger",
) -> int:
    created = await fetch(
        """
        INSERT INTO seller_parts (
            seller_id,
            car_id,
            template_id,
            category,
            name,
            description,
            status,
            sort_order
        )
        SELECT
            $1::BIGINT,
            $2::BIGINT,
            pt.id,
            pt.category,
            pt.name,
            CASE
                WHEN COALESCE(NULLIF(TRIM(sc.description), ''), '') <> '' THEN sc.description
                WHEN COALESCE(NULLIF(TRIM(pt.name), ''), '') <> '' THEN
                    pt.name || ' для ' || b.name || ' ' || m.name || '.

Авто розбирається на запчастини.

• оригінальні деталі
• фото та стан уточнюйте
• можливий підбір інших деталей

Сумісність уточнюйте перед замовленням.'
                ELSE
                    'Запчастина для ' || b.name || ' ' || m.name || '.

Авто розбирається на запчастини.

• оригінальні деталі
• фото та стан уточнюйте
• можливий підбір інших деталей

Сумісність уточнюйте перед замовленням.'
            END,
            'draft',
            pt.sort_order
        FROM part_templates pt
        JOIN seller_cars sc ON sc.id = $2::BIGINT AND sc.seller_id = $1::BIGINT
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE pt.vehicle_type = $3::TEXT
          AND pt.is_active = TRUE
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        seller_id,
        car_id,
        vehicle_type,
    )

    return len(created or [])


async def get_car_part_categories(car_id: int) -> list:
    return await fetch(
        """
        SELECT
            category,
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE status = 'available')::int AS active
        FROM seller_parts
        WHERE car_id = $1
        GROUP BY category
        ORDER BY MIN(sort_order), category
        """,
        car_id,
    )


async def get_parts_by_car_and_category(car_id: int, category: str) -> list:
    return await fetch(
        """
        SELECT
            id,
            seller_id,
            car_id,
            category,
            name,
            status,
            price,
            photo_id,
            description,
            sort_order
        FROM seller_parts
        WHERE car_id = $1
          AND category = $2
        ORDER BY sort_order, name
        """,
        car_id,
        category,
    )


async def get_part_by_id(part_id: int) -> dict | None:
    row = await fetchrow(
        """
        SELECT
            sp.*,
            m.name AS model,
            b.name AS brand
        FROM seller_parts sp
        JOIN seller_cars sc ON sc.id = sp.car_id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sp.id = $1
        """,
        part_id,
    )

    return dict(row) if row else None


async def update_part_status(part_id: int, seller_id: int, status: str):
    if status not in VALID_PART_STATUSES:
        return False

    row = await fetchrow(
        """
        UPDATE seller_parts
        SET status = $1,
            updated_at = NOW()
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        status,
        part_id,
        seller_id,
    )

    return bool(row)


async def update_part_price(part_id: int, seller_id: int, price: Decimal):
    row = await fetchrow(
        """
        UPDATE seller_parts
        SET price = $1,
            updated_at = NOW()
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        price,
        part_id,
        seller_id,
    )

    return bool(row)


async def update_part_description(part_id: int, seller_id: int, description: str):
    row = await fetchrow(
        """
        UPDATE seller_parts
        SET description = $1,
            updated_at = NOW()
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        description,
        part_id,
        seller_id,
    )

    return bool(row)


async def update_part_photo(part_id: int, seller_id: int, photo_id: str):
    row = await fetchrow(
        """
        UPDATE seller_parts
        SET photo_id = $1,
            updated_at = NOW()
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        photo_id,
        part_id,
        seller_id,
    )

    return bool(row)


async def get_seller_parts(
    seller_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list:
    if status:
        return await fetch(
            """
            SELECT
                sp.*,
                m.name AS model,
                b.name AS brand
            FROM seller_parts sp
            JOIN seller_cars sc ON sc.id = sp.car_id
            JOIN models m ON m.id = sc.model_id
            JOIN brands b ON b.id = m.brand_id
            WHERE sp.seller_id = $1
              AND sp.status = $2
            ORDER BY sp.created_at DESC
            LIMIT $3
            """,
            seller_id,
            status,
            limit,
        )

    return await fetch(
        """
        SELECT
            sp.*,
            m.name AS model,
            b.name AS brand
        FROM seller_parts sp
        JOIN seller_cars sc ON sc.id = sp.car_id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sp.seller_id = $1
        ORDER BY sp.created_at DESC
        LIMIT $2
        """,
        seller_id,
        limit,
    )


async def get_available_parts_for_site(seller_id: int) -> list:
    return await fetch(
        """
        SELECT
            sp.id,
            sp.car_id,
            sp.category,
            sp.name,
            sp.price,
            sp.photo_id,
            sp.description,
            m.name AS model,
            b.name AS brand
        FROM seller_parts sp
        JOIN seller_cars sc ON sc.id = sp.car_id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sp.seller_id = $1
          AND sp.status = 'available'
        ORDER BY
            sc.id DESC,
            sp.category,
            sp.sort_order,
            sp.name
        LIMIT 500
        """,
        seller_id,
    )


async def count_parts_by_car(car_id: int) -> dict:
    row = await fetchrow(
        """
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE status = 'available')::int AS available,
            COUNT(*) FILTER (WHERE price IS NULL)::int AS no_price,
            COUNT(*) FILTER (
                WHERE photo_id IS NULL
                   OR photo_id = ''
            )::int AS no_photo
        FROM seller_parts
        WHERE car_id = $1
        """,
        car_id,
    )

    return dict(row) if row else {
        "total": 0,
        "available": 0,
        "no_price": 0,
        "no_photo": 0,
    }


async def hide_parts_by_car(seller_id: int, car_id: int) -> int:
    rows = await fetch(
        """
        UPDATE seller_parts
        SET status = 'hidden',
            updated_at = NOW()
        WHERE seller_id = $1
          AND car_id = $2
          AND status <> 'hidden'
        RETURNING id
        """,
        seller_id,
        car_id,
    )

    return len(rows or [])


async def seller_owns_car(seller_id: int, car_id: int) -> bool:
    row = await fetchrow(
        """
        SELECT 1
        FROM seller_cars
        WHERE id = $1
          AND seller_id = $2
        """,
        car_id,
        seller_id,
    )

    return bool(row)


async def get_parts_by_car_id(seller_id: int, car_id: int) -> list:
    return await fetch(
        """
        SELECT
            id,
            seller_id,
            car_id,
            category,
            name,
            status,
            price,
            photo_id,
            description,
            sort_order
        FROM seller_parts
        WHERE seller_id = $1
          AND car_id = $2
        ORDER BY
            category,
            sort_order,
            name
        LIMIT 500
        """,
        seller_id,
        car_id,
    )


async def get_parts_by_car_id_filtered(
    seller_id: int,
    car_id: int,
    status: str | None = None,
    q: str | None = None,
) -> list:
    return await fetch(
        """
        SELECT
            id,
            seller_id,
            car_id,
            category,
            name,
            status,
            price,
            photo_id,
            description,
            sort_order
        FROM seller_parts
        WHERE seller_id = $1
          AND car_id = $2
          AND ($3::TEXT IS NULL OR status = $3)
          AND (
                $4::TEXT IS NULL
                OR regexp_replace(lower(name), '\\s+', ' ', 'g')
                LIKE '%' || regexp_replace(lower($4), '\\s+', ' ', 'g') || '%'
          )
        ORDER BY
            category,
            CASE status
                WHEN 'available' THEN 1
                WHEN 'draft' THEN 2
                WHEN 'hidden' THEN 3
                WHEN 'sold' THEN 4
                ELSE 5
            END,
            name ASC
        LIMIT 500
        """,
        seller_id,
        car_id,
        status,
        q,
    )


async def update_generated_parts_status(
    seller_id: int,
    car_id: int,
    status: str,
) -> int:
    if status not in VALID_PART_STATUSES:
        return 0

    rows = await fetch(
        """
        UPDATE seller_parts
        SET status = $1,
            updated_at = NOW()
        WHERE seller_id = $2
          AND car_id = $3
          AND template_id IS NOT NULL
        RETURNING id
        """,
        status,
        seller_id,
        car_id,
    )

    return len(rows)


async def bulk_update_parts_status_by_category(
    seller_id: int,
    car_id: int,
    category: str,
    status: str,
) -> int:
    if status not in VALID_PART_STATUSES:
        return 0

    rows = await fetch(
        """
        UPDATE seller_parts
        SET status = $1,
            updated_at = NOW()
        WHERE seller_id = $2
          AND car_id = $3
          AND category = $4
        RETURNING id
        """,
        status,
        seller_id,
        car_id,
        category,
    )

    return len(rows)


async def get_parts_counters_by_car_ids(
    seller_id: int,
    car_ids: list[int],
) -> dict[int, dict]:
    if not car_ids:
        return {}

    rows = await fetch(
        """
        SELECT
            car_id,
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE status = 'available')::int AS available
        FROM seller_parts
        WHERE seller_id = $1
          AND car_id = ANY($2::INT[])
        GROUP BY car_id
        """,
        seller_id,
        car_ids,
    )

    return {
        int(row["car_id"]): {
            "total": int(row.get("total") or 0),
            "available": int(row.get("available") or 0),
        }
        for row in rows
    }


async def create_manual_part(
    seller_id: int,
    car_id: int,
    category: str,
    name: str,
    status: str = "available",
    price=None,
    description: str | None = None,
) -> dict | None:
    row = await fetchrow(
        """
        INSERT INTO seller_parts (
            seller_id,
            car_id,
            template_id,
            category,
            name,
            status,
            price,
            description,
            sort_order
        )
        SELECT
            $1::BIGINT,
            $2::BIGINT,
            NULL,
            $3::TEXT,
            $4::TEXT,
            $5::TEXT,
            $6,
            $7,
            9999
        WHERE EXISTS (
            SELECT 1
            FROM seller_cars
            WHERE id = $2::BIGINT
              AND seller_id = $1::BIGINT
        )
        ON CONFLICT DO NOTHING
        RETURNING id, seller_id, car_id
        """,
        seller_id,
        car_id,
        category,
        name,
        status,
        price,
        description,
    )

    return dict(row) if row else None


async def update_part_fields(
    part_id: int,
    seller_id: int,
    name: str,
    category: str,
    status: str,
    price=None,
    description=None,
) -> bool:
    if status not in VALID_PART_STATUSES:
        return False

    row = await fetchrow(
        """
        UPDATE seller_parts
        SET
            name = $1,
            category = $2,
            status = $3,
            price = $4,
            description = $5,
            updated_at = NOW()
        WHERE id = $6
          AND seller_id = $7
          AND NOT EXISTS (
            SELECT 1
            FROM seller_parts sp2
            WHERE sp2.car_id = seller_parts.car_id
              AND LOWER(sp2.name) = LOWER($1)
              AND sp2.id <> $6
          )
        RETURNING id
        """,
        name,
        category,
        status,
        price,
        description,
        part_id,
        seller_id,
    )

    return bool(row)
