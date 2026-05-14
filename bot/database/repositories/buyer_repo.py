from bot.database.base import execute, fetch, fetchrow

FAVORITE_TYPES = {"car", "seller", "service", "website"}
REQUEST_STATUSES = {"new", "viewed", "answered", "closed"}
HISTORY_TYPES = {"car", "seller", "service"}


def _validate(value: str, allowed: set[str], message: str) -> str:
    if value not in allowed:
        raise ValueError(message)
    return value


async def toggle_favorite(telegram_id: int, entity_type: str, entity_ref: str) -> bool:
    _validate(entity_type, FAVORITE_TYPES, "Invalid favorite type")
    row = await fetchrow(
        """
        DELETE FROM buyer_favorites
        WHERE telegram_id = $1 AND entity_type = $2 AND entity_ref = $3
        RETURNING id
        """,
        telegram_id,
        entity_type,
        str(entity_ref),
    )
    if row:
        return False

    await execute(
        """
        INSERT INTO buyer_favorites (telegram_id, entity_type, entity_ref)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id, entity_type, entity_ref) DO NOTHING
        """,
        telegram_id,
        entity_type,
        str(entity_ref),
    )
    return True


async def is_favorite(telegram_id: int, entity_type: str, entity_ref: str) -> bool:
    _validate(entity_type, FAVORITE_TYPES, "Invalid favorite type")
    row = await fetchrow(
        """
        SELECT id FROM buyer_favorites
        WHERE telegram_id = $1 AND entity_type = $2 AND entity_ref = $3
        LIMIT 1
        """,
        telegram_id,
        entity_type,
        str(entity_ref),
    )
    return bool(row)


async def list_favorites(telegram_id: int, limit: int = 30):
    return await fetch(
        """
        SELECT id, entity_type, entity_ref, created_at
        FROM buyer_favorites
        WHERE telegram_id = $1
        ORDER BY created_at DESC, id DESC
        LIMIT $2
        """,
        telegram_id,
        limit,
    )


async def get_favorite(favorite_id: int, telegram_id: int):
    return await fetchrow(
        """
        SELECT id, entity_type, entity_ref, created_at
        FROM buyer_favorites
        WHERE id = $1 AND telegram_id = $2
        LIMIT 1
        """,
        favorite_id,
        telegram_id,
    )


async def delete_favorite(favorite_id: int, telegram_id: int) -> bool:
    row = await fetchrow(
        """
        DELETE FROM buyer_favorites
        WHERE id = $1 AND telegram_id = $2
        RETURNING id
        """,
        favorite_id,
        telegram_id,
    )
    return bool(row)


async def create_buyer_request(
    telegram_id: int,
    request_type: str,
    entity_type: str,
    entity_ref: str,
    seller_id: int | None = None,
    message: str | None = None,
):
    return await fetchrow(
        """
        INSERT INTO buyer_requests (
            telegram_id, request_type, entity_type, entity_ref, seller_id, message
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, telegram_id, request_type, entity_type, entity_ref, seller_id,
                  status, message, created_at, updated_at
        """,
        telegram_id,
        request_type,
        entity_type,
        str(entity_ref),
        seller_id,
        message,
    )


async def list_buyer_requests(telegram_id: int, limit: int = 20):
    return await fetch(
        """
        SELECT br.id, br.telegram_id, br.request_type, br.entity_type, br.entity_ref,
               br.seller_id, br.status, br.message, br.created_at, br.updated_at,
               s.shop_name, s.name AS seller_name, s.username AS seller_username,
               s.phone AS seller_phone
        FROM buyer_requests br
        LEFT JOIN sellers s ON s.id = br.seller_id
        WHERE br.telegram_id = $1
        ORDER BY br.created_at DESC, br.id DESC
        LIMIT $2
        """,
        telegram_id,
        limit,
    )


async def get_buyer_request(request_id: int, telegram_id: int):
    return await fetchrow(
        """
        SELECT br.id, br.telegram_id, br.request_type, br.entity_type, br.entity_ref,
               br.seller_id, br.status, br.message, br.created_at, br.updated_at,
               s.shop_name, s.name AS seller_name, s.username AS seller_username,
               s.phone AS seller_phone
        FROM buyer_requests br
        LEFT JOIN sellers s ON s.id = br.seller_id
        WHERE br.id = $1 AND br.telegram_id = $2
        LIMIT 1
        """,
        request_id,
        telegram_id,
    )


async def update_buyer_request_status(request_id: int, telegram_id: int, status: str):
    _validate(status, REQUEST_STATUSES, "Invalid request status")
    return await fetchrow(
        """
        UPDATE buyer_requests
        SET status = $3, updated_at = NOW()
        WHERE id = $1 AND telegram_id = $2
        RETURNING id
        """,
        request_id,
        telegram_id,
        status,
    )


async def add_garage_entry(telegram_id: int, vehicle_name: str):
    return await fetchrow(
        """
        INSERT INTO buyer_garage (telegram_id, vehicle_name)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id, lower(vehicle_name)) DO UPDATE
        SET updated_at = NOW()
        RETURNING id, telegram_id, vehicle_name, created_at, updated_at
        """,
        telegram_id,
        vehicle_name.strip(),
    )


async def list_garage(telegram_id: int):
    return await fetch(
        """
        SELECT id, telegram_id, vehicle_name, created_at, updated_at
        FROM buyer_garage
        WHERE telegram_id = $1
        ORDER BY updated_at DESC, id DESC
        """,
        telegram_id,
    )


async def get_garage_entry(entry_id: int, telegram_id: int):
    return await fetchrow(
        """
        SELECT id, telegram_id, vehicle_name, created_at, updated_at
        FROM buyer_garage
        WHERE id = $1 AND telegram_id = $2
        LIMIT 1
        """,
        entry_id,
        telegram_id,
    )


async def delete_garage_entry(entry_id: int, telegram_id: int) -> bool:
    row = await fetchrow(
        """
        DELETE FROM buyer_garage
        WHERE id = $1 AND telegram_id = $2
        RETURNING id
        """,
        entry_id,
        telegram_id,
    )
    return bool(row)


async def add_history(telegram_id: int, entity_type: str, entity_ref: str):
    _validate(entity_type, HISTORY_TYPES, "Invalid history type")
    return await fetchrow(
        """
        INSERT INTO buyer_history (telegram_id, entity_type, entity_ref)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id, entity_type, entity_ref) DO UPDATE
        SET viewed_at = NOW()
        RETURNING id, telegram_id, entity_type, entity_ref, viewed_at
        """,
        telegram_id,
        entity_type,
        str(entity_ref),
    )


async def list_history(telegram_id: int, limit: int = 10):
    return await fetch(
        """
        SELECT id, entity_type, entity_ref, viewed_at
        FROM buyer_history
        WHERE telegram_id = $1
        ORDER BY viewed_at DESC, id DESC
        LIMIT $2
        """,
        telegram_id,
        limit,
    )
