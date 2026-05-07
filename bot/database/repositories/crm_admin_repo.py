from bot.database.base import fetch, fetchrow


ALLOWED_ADMIN_ROLES = {"super_admin", "admin", "manager"}


def validate_admin_role(role: str) -> str:
    if role not in ALLOWED_ADMIN_ROLES:
        raise ValueError("Invalid admin role")
    return role


async def list_admin_users():
    return await fetch(
        """
        SELECT id, telegram_id, username, role, is_active, created_at
        FROM admin_users
        ORDER BY id ASC
        """,
    )


async def get_admin_user(admin_id: int):
    return await fetchrow(
        """
        SELECT id, telegram_id, username, role, is_active, created_at
        FROM admin_users
        WHERE id = $1
        LIMIT 1
        """,
        admin_id,
    )


async def get_admin_user_by_telegram_id(telegram_id: int):
    return await fetchrow(
        """
        SELECT id, telegram_id, username, role, is_active, created_at
        FROM admin_users
        WHERE telegram_id = $1
        LIMIT 1
        """,
        telegram_id,
    )


async def create_admin_user(telegram_id: int, username: str | None, role: str):
    validate_admin_role(role)

    return await fetchrow(
        """
        INSERT INTO admin_users (telegram_id, username, role)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id) DO NOTHING
        RETURNING id, telegram_id, username, role, is_active, created_at
        """,
        telegram_id,
        username,
        role,
    )


async def update_admin_user_role(admin_id: int, role: str):
    validate_admin_role(role)

    return await fetchrow(
        """
        UPDATE admin_users
        SET role = $2
        WHERE id = $1
        RETURNING id, telegram_id, username, role, is_active, created_at
        """,
        admin_id,
        role,
    )


async def set_admin_user_active(admin_id: int, is_active: bool):
    return await fetchrow(
        """
        UPDATE admin_users
        SET is_active = $2
        WHERE id = $1
        RETURNING id, telegram_id, username, role, is_active, created_at
        """,
        admin_id,
        is_active,
    )
