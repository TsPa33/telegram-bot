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
        SELECT *
        FROM seller_products
        WHERE id = $1
          AND seller_id = $2
        LIMIT 1
        """,
        product_id,
        seller_id,
    )


async def get_seller_products(
    seller_id: int,
    *,
    status: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    normalized_limit = max(1, min(int(limit or 50), 100))
    normalized_offset = max(0, int(offset or 0))
    args = [seller_id]
    filters = ["seller_id = $1"]

    if status is not None:
        _validate_status(status)
        args.append(status)
        filters.append(f"status = ${len(args)}")
    elif not include_archived:
        filters.append("status <> 'archived'")

    args.extend([normalized_limit, normalized_offset])
    limit_arg = len(args) - 1
    offset_arg = len(args)

    return await fetch(
        f"""
        SELECT *
        FROM seller_products
        WHERE {' AND '.join(filters)}
        ORDER BY created_at DESC, id DESC
        LIMIT ${limit_arg} OFFSET ${offset_arg}
        """,
        *args,
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
