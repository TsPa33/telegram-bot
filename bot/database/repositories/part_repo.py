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


async def generate_parts_for_car(seller_id: int, car_id: int, vehicle_type: str = "passenger") -> int:
    created = await fetch(
        """
        INSERT INTO seller_parts (
            seller_id, car_id, template_id, category, name, status, sort_order
        )
        SELECT
            $1, $2, pt.id, pt.category, pt.name, 'draft', pt.sort_order
        FROM part_templates pt
        WHERE pt.vehicle_type = $3
          AND pt.is_active = TRUE
          AND EXISTS (
            SELECT 1
            FROM seller_cars sc
            WHERE sc.id = $2
              AND sc.seller_id = $1
          )
        ON CONFLICT (car_id, name) DO NOTHING
        RETURNING id
        """,
        seller_id,
        car_id,
        vehicle_type,
    )
    return len(created)


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
        SELECT id, seller_id, car_id, category, name, status, price, photo_id, description, sort_order
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
            sp.*, m.name AS model, b.name AS brand
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
        SET status = $1, updated_at = NOW()
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
        SET price = $1, updated_at = NOW()
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
        SET description = $1, updated_at = NOW()
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
        SET photo_id = $1, updated_at = NOW()
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        photo_id,
        part_id,
        seller_id,
    )
    return bool(row)


async def get_seller_parts(seller_id: int, status: str | None = None, limit: int = 100) -> list:
    if status:
        return await fetch(
            """
            SELECT sp.*, m.name AS model, b.name AS brand
            FROM seller_parts sp
            JOIN seller_cars sc ON sc.id = sp.car_id
            JOIN models m ON m.id = sc.model_id
            JOIN brands b ON b.id = m.brand_id
            WHERE sp.seller_id = $1 AND sp.status = $2
            ORDER BY sp.created_at DESC
            LIMIT $3
            """,
            seller_id,
            status,
            limit,
        )
    return await fetch(
        """
        SELECT sp.*, m.name AS model, b.name AS brand
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
        SELECT sp.id, sp.car_id, sp.category, sp.name, sp.price, sp.photo_id, sp.description,
               m.name AS model, b.name AS brand
        FROM seller_parts sp
        JOIN seller_cars sc ON sc.id = sp.car_id
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sp.seller_id = $1
          AND sp.status = 'available'
        ORDER BY sc.id DESC, sp.category, sp.sort_order, sp.name
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
            COUNT(*) FILTER (WHERE photo_id IS NULL OR photo_id = '')::int AS no_photo
        FROM seller_parts
        WHERE car_id = $1
        """,
        car_id,
    )
    return dict(row) if row else {"total": 0, "available": 0, "no_price": 0, "no_photo": 0}


async def seller_owns_car(seller_id: int, car_id: int) -> bool:
    row = await fetchrow("SELECT 1 FROM seller_cars WHERE id = $1 AND seller_id = $2", car_id, seller_id)
    return bool(row)
