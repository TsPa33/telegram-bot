import json

from bot.database.base import execute, fetchrow


ADMIN_FIELDS = "id, telegram_id, username, role, is_active, password_hash, created_at"


async def get_admin_by_telegram_id(telegram_id: int):
    return await fetchrow(
        f"""
        SELECT {ADMIN_FIELDS}
        FROM admin_users
        WHERE telegram_id = $1
        LIMIT 1
        """,
        telegram_id,
    )


async def get_admin_by_username(username: str):
    return await fetchrow(
        f"""
        SELECT {ADMIN_FIELDS}
        FROM admin_users
        WHERE LOWER(username) = LOWER($1)
          AND is_active = TRUE
        LIMIT 1
        """,
        username,
    )


async def create_admin_session(telegram_id: int, token: str, expires_at):
    return await fetchrow(
        """
        INSERT INTO admin_sessions (admin_user_id, token, expires_at)
        SELECT id, $2, $3
        FROM admin_users
        WHERE telegram_id = $1
          AND is_active = TRUE
        RETURNING id, admin_user_id, token, expires_at, used_at, created_at
        """,
        telegram_id,
        token,
        expires_at,
    )


async def create_admin_session_by_admin_id(
    admin_id: int,
    token: str,
    expires_at,
    used: bool = True,
):
    return await fetchrow(
        """
        INSERT INTO admin_sessions (admin_user_id, token, expires_at, used_at)
        VALUES ($1, $2, $3, CASE WHEN $4 THEN NOW() ELSE NULL END)
        RETURNING id, admin_user_id, token, expires_at, used_at, created_at
        """,
        admin_id,
        token,
        expires_at,
        used,
    )


async def get_session_by_token(token: str):
    return await fetchrow(
        """
        SELECT id, admin_user_id, token, expires_at, used_at, created_at
        FROM admin_sessions
        WHERE token = $1
        LIMIT 1
        """,
        token,
    )


async def mark_session_used(token: str):
    return await fetchrow(
        """
        UPDATE admin_sessions
        SET used_at = NOW()
        WHERE token = $1
        RETURNING id, admin_user_id, token, expires_at, used_at, created_at
        """,
        token,
    )


async def get_admin_by_id(admin_id: int):
    return await fetchrow(
        f"""
        SELECT {ADMIN_FIELDS}
        FROM admin_users
        WHERE id = $1
        LIMIT 1
        """,
        admin_id,
    )


async def set_admin_password(admin_id: int, password_hash: str):
    return await fetchrow(
        f"""
        UPDATE admin_users
        SET password_hash = $2
        WHERE id = $1
        RETURNING {ADMIN_FIELDS}
        """,
        admin_id,
        password_hash,
    )


async def log_admin_action(
    actor_admin_id,
    action,
    entity_type=None,
    entity_id=None,
    payload=None,
    ip=None,
    user_agent=None,
):
    payload_json = json.dumps(payload or {})

    return await fetchrow(
        """
        INSERT INTO admin_audit_logs (
            actor_admin_id,
            action,
            entity_type,
            entity_id,
            payload,
            ip,
            user_agent
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
        RETURNING id, actor_admin_id, action, entity_type, entity_id,
                  payload, ip, user_agent, created_at
        """,
        actor_admin_id,
        action,
        entity_type,
        entity_id,
        payload_json,
        ip,
        user_agent,
    )
