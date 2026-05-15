from bot.database.base import fetch


async def _get_payment_columns():
    rows = await fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'payments'
        """
    )
    return {row["column_name"] for row in rows}


async def list_crm_payments(
    status: str | None = None,
    product: str | None = None,
    seller_id: int | None = None,
    limit: int = 100,
):
    columns = await _get_payment_columns()
    filters = []
    args = []

    def select_column(column_name: str, alias: str | None = None):
        if column_name in columns:
            return f"p.{column_name}" + (f" AS {alias}" if alias else "")
        return f"NULL AS {alias or column_name}"

    if status and "status" in columns:
        args.append(status)
        filters.append(f"p.status = ${len(args)}")

    if product:
        if "product_type" in columns and "product" in columns:
            args.append(product)
            filters.append(f"COALESCE(p.product_type, p.product) = ${len(args)}")
        elif "product_type" in columns:
            args.append(product)
            filters.append(f"p.product_type = ${len(args)}")
        elif "product" in columns:
            args.append(product)
            filters.append(f"p.product = ${len(args)}")

    if seller_id is not None and "seller_id" in columns:
        args.append(seller_id)
        filters.append(f"p.seller_id = ${len(args)}")

    if "product_type" in columns and "product" in columns:
        product_select_sql = "COALESCE(p.product_type, p.product) AS product"
    elif "product_type" in columns:
        product_select_sql = select_column("product_type", "product")
    else:
        product_select_sql = select_column("product", "product")

    args.append(limit)
    limit_param = f"${len(args)}"
    where_sql = ""

    if filters:
        where_sql = "WHERE " + " AND ".join(filters)

    order_sql = "p.created_at DESC, p.id DESC" if "created_at" in columns else "p.id DESC"
    if "seller_id" in columns:
        join_sql = "LEFT JOIN sellers s ON s.id = p.seller_id"
        seller_username_sql = "s.username AS seller_username"
        seller_shop_name_sql = "s.shop_name AS seller_shop_name"
    else:
        join_sql = ""
        seller_username_sql = "NULL AS seller_username"
        seller_shop_name_sql = "NULL AS seller_shop_name"

    return await fetch(
        f"""
        SELECT
            {select_column("id")},
            {select_column("seller_id")},
            {seller_username_sql},
            {seller_shop_name_sql},
            {product_select_sql},
            {select_column("amount")},
            {select_column("status")},
            {select_column("created_at")},
            {select_column("updated_at")},
            {select_column("paid_at")},
            {select_column("order_id")},
            {select_column("payment_id", "raw_payment_id")}
        FROM payments p
        {join_sql}
        {where_sql}
        ORDER BY {order_sql}
        LIMIT {limit_param}
        """,
        *args,
    )
