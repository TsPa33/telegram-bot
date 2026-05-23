from decimal import Decimal

from bot.database.base import fetch, fetchrow

VALID_PART_STATUSES = {"draft", "available", "sold", "hidden"}

DEFAULT_CATEGORY_UK_MAP = {
    "Body": "Кузов",
    "Optics": "Оптика",
    "Engine": "Двигун",
    "Interior": "Салон",
    "Suspension": "Підвіска",
    "Electrical": "Електрика",
    "Transmission": "Трансмісія",
    "Cooling / AC": "Охолодження",
}

DEFAULT_PART_NAME_UK_MAP = {
    "Front bumper": "Передній бампер",
    "Rear bumper": "Задній бампер",
    "Front left door": "Передні ліві двері",
    "Front right door": "Передні праві двері",
    "Rear left door": "Задні ліві двері",
    "Rear right door": "Задні праві двері",
    "Hood": "Капот",
    "Trunk": "Кришка багажника",
    "Trunk lid": "Кришка багажника",
    "Fender": "Крило",
    "Front left fender": "Переднє ліве крило",
    "Front right fender": "Переднє праве крило",
    "Headlight": "Фара",
    "Left headlight": "Ліва фара",
    "Right headlight": "Права фара",
    "Taillight": "Задній ліхтар",
    "Left tail light": "Лівий задній ліхтар",
    "Right tail light": "Правий задній ліхтар",
    "Engine": "Двигун",
    "Complete engine": "Двигун у зборі",
    "Transmission": "КПП",
    "Manual gearbox": "МКПП",
    "Automatic gearbox": "АКПП",
    "Turbocharger": "Турбіна",
    "Radiator": "Радіатор",
    "Main radiator": "Основний радіатор",
    "Mirror": "Дзеркало",
    "Left mirror": "Ліве дзеркало",
    "Right mirror": "Праве дзеркало",
    "Steering wheel": "Кермо",
    "Dashboard": "Торпедо",
    "Seat": "Сидіння",
    "Driver seat": "Сидіння водія",
    "Passenger seat": "Сидіння пасажира",
    "Bumper reinforcement": "Підсилювач бампера",
}


def _to_uk_category(category: str | None) -> str:
    return DEFAULT_CATEGORY_UK_MAP.get((category or "").strip(), (category or "").strip())


def _to_uk_part_name(name: str | None) -> str:
    return DEFAULT_PART_NAME_UK_MAP.get((name or "").strip(), (name or "").strip())


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
    templates = await get_active_part_templates(vehicle_type)
    if not templates:
        return 0

    for template in templates:
        template["category"] = _to_uk_category(template.get("category"))
        template["name"] = _to_uk_part_name(template.get("name"))

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
            t.id,
            t.category,
            t.name,
            CASE
                WHEN COALESCE(NULLIF(TRIM(sc.description), ''), '') <> '' THEN sc.description
                WHEN COALESCE(NULLIF(TRIM(t.name), ''), '') <> '' THEN
                    t.name || '. Запчастина з авто ' || b.name || ' ' || m.name || '. Уточнюйте стан, сумісність та комплектацію.'
                ELSE
                    'Запчастина з авто ' || b.name || ' ' || m.name || '. Уточнюйте стан, сумісність та комплектацію.'
            END,
            'draft',
            t.sort_order
        FROM jsonb_to_recordset($3::jsonb) AS t(id BIGINT, category TEXT, name TEXT, sort_order INT)
        JOIN seller_cars sc ON sc.id = $2::BIGINT AND sc.seller_id = $1::BIGINT
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        seller_id,
        car_id,
        templates,
    )

    return len(created or [])


async def normalize_generated_parts_to_ukrainian() -> None:
    for en_name, uk_name in DEFAULT_PART_NAME_UK_MAP.items():
        await fetch(
            """
            UPDATE seller_parts
            SET name = $1,
                updated_at = NOW()
            WHERE name = $2
              AND (template_id IS NOT NULL OR description ILIKE '%Авто розбирається на запчастини%')
            """,
            uk_name,
            en_name,
        )

    for en_category, uk_category in DEFAULT_CATEGORY_UK_MAP.items():
        await fetch(
            """
            UPDATE seller_parts
            SET category = $1,
                updated_at = NOW()
            WHERE category = $2
              AND (template_id IS NOT NULL OR description ILIKE '%Авто розбирається на запчастини%')
            """,
            uk_category,
            en_category,
        )


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


async def search_available_parts_for_buyer(query: str, limit: int = 100) -> list:
    pattern = f"%{(query or '').strip()}%"
    return await fetch(
        """
        SELECT
            s.id AS seller_id,
            s.shop_name,
            s.name,
            s.phone,
            s.username,
            s.city,
            s.website,
            ss.subdomain AS site_subdomain,
            s.photo_id AS seller_photo_id,
            s.is_verified,
            sp.id AS part_id,
            sp.name AS part_name,
            sp.category AS part_category,
            sp.price AS part_price,
            sp.photo_id AS part_photo_id,
            sp.description AS part_description,
            sc.id AS car_id,
            b.name AS brand,
            m.name AS model,
            sc.photo_id AS car_photo_id
        FROM seller_parts sp
        JOIN seller_cars sc ON sc.id = sp.car_id
        JOIN sellers s ON s.id = sp.seller_id
        LEFT JOIN seller_sites ss ON ss.seller_id = s.id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sp.status = 'available'
          AND sc.status::text IN ('active', '1', 'true', 'enabled', 'published')
          AND (
                LOWER(COALESCE(sp.name, '')) LIKE LOWER($1)
             OR LOWER(COALESCE(sp.category, '')) LIKE LOWER($1)
             OR LOWER(COALESCE(sp.description, '')) LIKE LOWER($1)
             OR LOWER(COALESCE(b.name, '')) LIKE LOWER($1)
             OR LOWER(COALESCE(m.name, '')) LIKE LOWER($1)
          )
        ORDER BY sp.updated_at DESC NULLS LAST, sp.id DESC
        LIMIT $2
        """,
        pattern,
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
