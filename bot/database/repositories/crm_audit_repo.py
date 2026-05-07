from bot.database.base import fetch


async def list_admin_audit_logs(
    action: str | None = None,
    actor_admin_id: int | None = None,
    limit: int = 200,
):
    return await fetch(
        """
        SELECT
            logs.id,
            logs.actor_admin_id,
            admins.username AS actor_username,
            admins.telegram_id AS actor_telegram_id,
            logs.action,
            logs.entity_type,
            logs.entity_id,
            logs.payload,
            logs.ip,
            logs.user_agent,
            logs.created_at
        FROM admin_audit_logs logs
        LEFT JOIN admin_users admins ON admins.id = logs.actor_admin_id
        WHERE ($1::text IS NULL OR logs.action = $1)
          AND ($2::integer IS NULL OR logs.actor_admin_id = $2)
        ORDER BY logs.created_at DESC, logs.id DESC
        LIMIT $3
        """,
        action,
        actor_admin_id,
        limit,
    )
