from typing import Any

from bot.database.base import fetch, fetchrow


PRODUCT_STATUSES = {"active", "inactive", "archived"}
PRODUCT_STOCK_STATUSES = {"available", "low_stock", "sold", "preorder"}
_PRODUCT_UPDATE_FIELDS = {
    "donor_car_id",
    "title",
    "category",
    "brand",
    "model",
    "oem_code",
    "condition",
    "description",
    "price",
    "quantity",
    "stock_status",
    "photo_url",
    "status",
}


def _validate_status(status: str) -> None:
    if status not in PRODUCT_STATUSES:
        raise ValueError("Invalid product status")


def _validate_stock_status(stock_status: str) -> None:
    if stock_status not in PRODUCT_STOCK_STATUSES:
        raise ValueError("Invalid product stock status")


def _clean_required(value: str, field_name: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _clean_optional(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return value


async def create_product(
    *,
    seller_id: int,
    title: str,
    category: str,
    donor_car_id: int | None = None,
    brand: str | None = None,
    model: str | None = None,
    oem_code: str | None = None,
    condition: str | None = None,
    description: str | None = None,
    price=None,
    quantity: int = 1,
    stock_status: str = "available",
    photo_url: str | None = None,
    status: str = "active",
):
    _validate_status(status)
    _validate_stock_status(stock_status)

    return await fetchrow(
        """
        INSERT INTO seller_products (
            seller_id, donor_car_id, title, category, brand, model, oem_code,
            condition, description, price, quantity, stock_status, photo_url, status
        )
        SELECT
            $1, $2, $3, $4, $5, $6, $7,
            $8, $9, $10, $11, $12, $13, $14
        WHERE $2::integer IS NULL
           OR EXISTS (
               SELECT 1
               FROM seller_cars sc
               WHERE sc.id = $2
                 AND sc.seller_id = $1
           )
        RETURNING *
        """,
        seller_id,
        donor_car_id,
        _clean_required(title, "title"),
        _clean_required(category, "category"),
        _clean_optional(brand),
        _clean_optional(model),
        _clean_optional(oem_code),
        _clean_optional(condition),
        _clean_optional(description),
        price,
        quantity,
        stock_status,
        _clean_optional(photo_url),
        status,
    )


async def update_product(seller_id: int, product_id: int, **fields):
    invalid_fields = set(fields) - _PRODUCT_UPDATE_FIELDS
    if invalid_fields:
        raise ValueError(f"Unsupported product fields: {', '.join(sorted(invalid_fields))}")

    if "title" in fields:
        fields["title"] = _clean_required(fields["title"], "title")
    if "category" in fields:
        fields["category"] = _clean_required(fields["category"], "category")
    if "status" in fields:
        _validate_status(fields["status"])
    if "stock_status" in fields:
        _validate_stock_status(fields["stock_status"])

    if not fields:
        return await get_product_by_id(seller_id, product_id)

    assignments = []
    args = []
    for column, value in fields.items():
        args.append(_clean_optional(value))
        assignments.append(f"{column} = ${len(args)}")

    args.extend([product_id, seller_id])
    product_id_arg = len(args) - 1
    seller_id_arg = len(args)
    donor_guard = ""

    if "donor_car_id" in fields:
        donor_car_id = fields["donor_car_id"]
        if donor_car_id is not None:
            args.append(donor_car_id)
            donor_arg = len(args)
            donor_guard = f"""
          AND EXISTS (
              SELECT 1
              FROM seller_cars sc
              WHERE sc.id = ${donor_arg}
                AND sc.seller_id = ${seller_id_arg}
          )"""

    return await fetchrow(
        f"""
        UPDATE seller_products
        SET {', '.join(assignments)},
            updated_at = NOW()
        WHERE id = ${product_id_arg}
          AND seller_id = ${seller_id_arg}
          {donor_guard}
        RETURNING *
        """,
        *args,
    )


async def get_product_by_id(seller_id: int, product_id: int):
    return await fetchrow(
        """
        SELECT
            sp.*,
            b.name AS donor_brand,
            m.name AS donor_model
        FROM seller_products sp
        LEFT JOIN seller_cars sc ON sc.id = sp.donor_car_id AND sc.seller_id = sp.seller_id
        LEFT JOIN models m ON m.id = sc.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        WHERE sp.id = $1
          AND sp.seller_id = $2
        LIMIT 1
        """,
        product_id,
        seller_id,
    )


async def get_product_by_title_oem(seller_id: int, title: str, oem_code: str | None):
    clean_title = _clean_required(title, "title")
    clean_oem_code = _clean_optional(oem_code)
    if not clean_oem_code:
        return None

    return await fetchrow(
        """
        SELECT *
        FROM seller_products
        WHERE seller_id = $1
          AND LOWER(title) = LOWER($2)
          AND LOWER(oem_code) = LOWER($3)
          AND status <> 'archived'
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        seller_id,
        clean_title,
        clean_oem_code,
    )


def _product_inventory_filters(
    args: list,
    *,
    query: str | None = None,
    inventory_status: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    model: str | None = None,
) -> list[str]:
    filters: list[str] = []
    normalized_query = str(query or "").strip()
    if normalized_query:
        args.append(f"%{normalized_query}%")
        idx = len(args)
        filters.append(
            "("
            f"sp.title ILIKE ${idx} OR sp.category ILIKE ${idx} OR "
            f"sp.brand ILIKE ${idx} OR sp.model ILIKE ${idx} OR "
            f"sp.oem_code ILIKE ${idx} OR sp.description ILIKE ${idx} OR "
            f"b.name ILIKE ${idx} OR m.name ILIKE ${idx}"
            ")"
        )
    if category:
        args.append(str(category).strip())
        filters.append(f"sp.category = ${len(args)}")
    if brand:
        args.append(str(brand).strip())
        filters.append(f"COALESCE(sp.brand, b.name, '') = ${len(args)}")
    if model:
        args.append(str(model).strip())
        filters.append(f"COALESCE(sp.model, m.name, '') = ${len(args)}")
    normalized_status = str(inventory_status or "").strip().lower()
    if normalized_status == "available":
        filters.append("sp.status = 'active'")
        filters.append("sp.stock_status = 'available'")
    elif normalized_status == "sold":
        filters.append("sp.status = 'active'")
        filters.append("sp.stock_status = 'sold'")
    elif normalized_status == "hidden":
        filters.append("sp.status = 'inactive'")
    return filters


async def get_seller_products(
    seller_id: int,
    *,
    status: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    sort: str = "newest",
    query: str | None = None,
    inventory_status: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    model: str | None = None,
):
    normalized_limit = max(1, min(int(limit or 50), 500))
    normalized_offset = max(0, int(offset or 0))
    args = [seller_id]
    filters = ["sp.seller_id = $1"]

    if status is not None:
        _validate_status(status)
        args.append(status)
        filters.append(f"sp.status = ${len(args)}")
    elif not include_archived:
        filters.append("sp.status <> 'archived'")

    filters.extend(_product_inventory_filters(args, query=query, inventory_status=inventory_status, category=category, brand=brand, model=model))

    prefixed_filters = filters

    args.extend([normalized_limit, normalized_offset])
    limit_arg = len(args) - 1
    offset_arg = len(args)

    return await fetch(
        f"""
        SELECT
            sp.*,
            b.name AS donor_brand,
            m.name AS donor_model
        FROM seller_products sp
        LEFT JOIN seller_cars sc ON sc.id = sp.donor_car_id AND sc.seller_id = sp.seller_id
        LEFT JOIN models m ON m.id = sc.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        WHERE {' AND '.join(prefixed_filters)}
        ORDER BY {_product_sort_sql(sort)}
        LIMIT ${limit_arg} OFFSET ${offset_arg}
        """,
        *args,
    )


async def search_seller_products(seller_id: int, query: str, limit: int = 100):
    normalized_limit = max(1, min(int(limit or 100), 200))
    normalized_offset = 0
    if isinstance(limit, tuple):
        normalized_limit, normalized_offset = limit
    q = f"%{(query or '').strip().lower()}%"
    return await fetch(
        """
        SELECT
            sp.*,
            b.name AS donor_brand,
            m.name AS donor_model
        FROM seller_products sp
        LEFT JOIN seller_cars sc ON sc.id = sp.donor_car_id AND sc.seller_id = sp.seller_id
        LEFT JOIN models m ON m.id = sc.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        WHERE sp.seller_id = $1
          AND sp.status <> 'archived'
          AND (
            LOWER(COALESCE(sp.title, '')) LIKE $2
            OR LOWER(COALESCE(sp.category, '')) LIKE $2
            OR LOWER(COALESCE(sp.brand, '')) LIKE $2
            OR LOWER(COALESCE(sp.model, '')) LIKE $2
            OR LOWER(COALESCE(sp.description, '')) LIKE $2
            OR LOWER(COALESCE(b.name, '')) LIKE $2
            OR LOWER(COALESCE(m.name, '')) LIKE $2
          )
        ORDER BY sp.created_at DESC, sp.id DESC
        LIMIT $3 OFFSET $4
        """,
        seller_id,
        q,
        normalized_limit,
        normalized_offset,
    )


def _product_filter_sql(filters: dict | None, args: list) -> str:
    filters = filters or {}
    clauses = []
    for key, col in [("category", "sp.category"), ("brand", "sp.brand"), ("model", "sp.model"), ("condition", "sp.condition"), ("availability", "sp.stock_status")]:
        value = str(filters.get(key) or "").strip()
        if value:
            args.append(value)
            clauses.append(f"LOWER(COALESCE({col}, '')) = LOWER(${len(args)})")
    return (" AND " + " AND ".join(clauses)) if clauses else ""


def _product_sort_sql(sort: str | None) -> str:
    normalized = (sort or "newest").strip().lower()
    sort_map = {
        "newest": "sp.created_at DESC, sp.id DESC",
        "oldest": "sp.created_at ASC, sp.id ASC",
        "name_asc": "LOWER(COALESCE(sp.title, '')) ASC, sp.id DESC",
        "name_desc": "LOWER(COALESCE(sp.title, '')) DESC, sp.id DESC",
        "price_asc": "sp.price ASC NULLS LAST, sp.id DESC",
        "price_desc": "sp.price DESC NULLS LAST, sp.id DESC",
    }
    return sort_map.get(normalized, sort_map["newest"])


async def search_seller_products_paginated(seller_id: int, query: str, *, limit: int = 100, offset: int = 0, filters: dict | None = None, sort: str = "newest"):
    normalized_limit = max(1, min(int(limit or 100), 200))
    normalized_offset = max(0, int(offset or 0))
    q = f"%{(query or '').strip().lower()}%"
    args = [seller_id, q]
    filters_sql = _product_filter_sql(filters, args)
    args.extend([normalized_limit, normalized_offset])
    return await fetch(
        f"""
        SELECT sp.*, b.name AS donor_brand, m.name AS donor_model
        FROM seller_products sp
        LEFT JOIN seller_cars sc ON sc.id = sp.donor_car_id AND sc.seller_id = sp.seller_id
        LEFT JOIN models m ON m.id = sc.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        WHERE sp.seller_id = $1
          AND sp.status <> 'archived'
          AND (
            LOWER(COALESCE(sp.title, '')) LIKE $2 OR LOWER(COALESCE(sp.category, '')) LIKE $2
            OR LOWER(COALESCE(sp.brand, '')) LIKE $2 OR LOWER(COALESCE(sp.model, '')) LIKE $2
            OR LOWER(COALESCE(sp.description, '')) LIKE $2 OR LOWER(COALESCE(b.name, '')) LIKE $2
            OR LOWER(COALESCE(m.name, '')) LIKE $2
          ){filters_sql}
        ORDER BY {_product_sort_sql(sort)}
        LIMIT ${len(args)-1} OFFSET ${len(args)}
        """,
        *args,
    )


async def count_search_seller_products(seller_id: int, query: str, filters: dict | None = None) -> int:
    q = f"%{(query or '').strip().lower()}%"
    args = [seller_id, q]
    filters_sql = _product_filter_sql(filters, args)
    row = await fetchrow(
        f"""
        SELECT COUNT(*)::int AS total
        FROM seller_products sp
        LEFT JOIN seller_cars sc ON sc.id = sp.donor_car_id AND sc.seller_id = sp.seller_id
        LEFT JOIN models m ON m.id = sc.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        WHERE sp.seller_id = $1
          AND sp.status <> 'archived'
          AND (
            LOWER(COALESCE(sp.title, '')) LIKE $2
            OR LOWER(COALESCE(sp.category, '')) LIKE $2
            OR LOWER(COALESCE(sp.brand, '')) LIKE $2
            OR LOWER(COALESCE(sp.model, '')) LIKE $2
            OR LOWER(COALESCE(sp.description, '')) LIKE $2
            OR LOWER(COALESCE(b.name, '')) LIKE $2
            OR LOWER(COALESCE(m.name, '')) LIKE $2
          ){filters_sql}
        """,
        *args,
    )
    return int((row or {}).get("total") or 0)


async def count_seller_products_for_site(seller_id: int, filters: dict | None = None) -> int:
    args=[seller_id]
    filters_sql=_product_filter_sql(filters,args)
    row = await fetchrow(
        f"""
        SELECT COUNT(*)::int AS total
        FROM seller_products
        WHERE seller_id = $1
          AND status <> 'archived'
          {filters_sql.replace('sp.', '')}
        """,
        *args,
    )
    return int((row or {}).get("total") or 0)


async def list_product_ids_for_sitemap(seller_id: int, limit: int = 5000):
    normalized_limit = max(1, min(int(limit or 5000), 5000))
    return await fetch(
        """
        SELECT sp.id
        FROM seller_products sp
        WHERE sp.seller_id = $1
          AND sp.status <> 'archived'
        ORDER BY sp.created_at DESC, sp.id DESC
        LIMIT $2
        """,
        seller_id,
        normalized_limit,
    )


async def get_seller_product_donor_cars(seller_id: int):
    return await fetch(
        """
        SELECT
            sc.id AS car_id,
            b.name AS brand,
            m.name AS model,
            sc.created_at
        FROM seller_cars sc
        JOIN models m ON m.id = sc.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sc.seller_id = $1
        ORDER BY sc.created_at DESC, sc.id DESC
        LIMIT 100
        """,
        seller_id,
    )


async def set_product_status(seller_id: int, product_id: int, status: str) -> bool:
    _validate_status(status)
    row = await fetchrow(
        """
        UPDATE seller_products
        SET status = $1,
            updated_at = NOW()
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        status,
        product_id,
        seller_id,
    )
    return row is not None


async def count_seller_product_inventory_statuses(seller_id: int):
    row = await fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE status <> 'archived')::int AS total,
            COUNT(*) FILTER (WHERE status = 'active' AND stock_status = 'available')::int AS available,
            COUNT(*) FILTER (WHERE status = 'active' AND stock_status = 'sold')::int AS sold,
            COUNT(*) FILTER (WHERE status = 'inactive')::int AS hidden
        FROM seller_products
        WHERE seller_id = $1
        """,
        seller_id,
    )
    return dict(row) if row else {"total": 0, "available": 0, "sold": 0, "hidden": 0}


async def list_seller_product_filter_options(seller_id: int):
    row = await fetchrow(
        """
        SELECT
            COALESCE(array_remove(array_agg(DISTINCT NULLIF(trim(category), '')), NULL), ARRAY[]::TEXT[]) AS categories,
            COALESCE(array_remove(array_agg(DISTINCT NULLIF(trim(COALESCE(brand, b.name)), '')), NULL), ARRAY[]::TEXT[]) AS brands,
            COALESCE(array_remove(array_agg(DISTINCT NULLIF(trim(COALESCE(model, m.name)), '')), NULL), ARRAY[]::TEXT[]) AS models
        FROM seller_products sp
        LEFT JOIN seller_cars sc ON sc.id = sp.donor_car_id AND sc.seller_id = sp.seller_id
        LEFT JOIN models m ON m.id = sc.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        WHERE sp.seller_id = $1
          AND sp.status <> 'archived'
        """,
        seller_id,
    )
    return {
        "categories": sorted(row.get("categories") or []) if row else [],
        "brands": sorted(row.get("brands") or []) if row else [],
        "models": sorted(row.get("models") or []) if row else [],
    }


async def bulk_update_products_inventory(seller_id: int, product_ids: list[int], *, status: str, stock_status: str | None = None) -> int:
    _validate_status(status)
    if stock_status is not None:
        _validate_stock_status(stock_status)
    ids = [int(item) for item in product_ids if str(item).strip()]
    if not ids:
        return 0
    row = await fetchrow(
        """
        WITH updated AS (
            UPDATE seller_products
            SET status = $3,
                stock_status = COALESCE($4, stock_status),
                updated_at = NOW()
            WHERE seller_id = $1
              AND id = ANY($2::BIGINT[])
              AND status <> 'archived'
            RETURNING id
        )
        SELECT COUNT(*)::int AS updated_count FROM updated
        """,
        seller_id,
        ids,
        status,
        stock_status,
    )
    return int(row.get("updated_count") or 0) if row else 0


async def bulk_archive_products(seller_id: int, product_ids: list[int]) -> int:
    ids = [int(item) for item in product_ids if str(item).strip()]
    if not ids:
        return 0
    row = await fetchrow(
        """
        WITH updated AS (
            UPDATE seller_products
            SET status = 'archived',
                updated_at = NOW()
            WHERE seller_id = $1
              AND id = ANY($2::BIGINT[])
              AND status <> 'archived'
            RETURNING id
        )
        SELECT COUNT(*)::int AS updated_count FROM updated
        """,
        seller_id,
        ids,
    )
    return int(row.get("updated_count") or 0) if row else 0


async def update_product_photo(
    seller_id: int,
    product_id: int,
    photo_url: str | None,
) -> bool:
    row = await fetchrow(
        """
        UPDATE seller_products
        SET photo_url = $1,
            updated_at = NOW()
        WHERE id = $2
          AND seller_id = $3
        RETURNING id
        """,
        _clean_optional(photo_url),
        product_id,
        seller_id,
    )
    return row is not None


async def delete_product_soft(seller_id: int, product_id: int) -> bool:
    return await set_product_status(seller_id, product_id, "archived")
