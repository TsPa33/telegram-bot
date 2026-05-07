import json

from bot.database.base import execute, fetchrow


async def get_admin_by_telegram_id(telegram_id: int):
    return await fetchrow(
        """
        SELECT id, telegram_id, username, role, is_active, created_at
        FROM admin_users
        WHERE telegram_id = $1
        LIMIT 1
        """,
        telegram_id,
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
        """
        SELECT id, telegram_id, username, role, is_active, created_at
        FROM admin_users
        WHERE id = $1
        LIMIT 1
        """,
        admin_id,
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
