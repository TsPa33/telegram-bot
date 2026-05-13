from bot.database.base import fetch, fetchrow, transaction

SUPPORT_STATUSES = {"open", "in_progress", "closed"}
SUPPORT_SENDER_TYPES = {"user", "admin", "system"}


def _validate_status(status: str) -> str:
    if status not in SUPPORT_STATUSES:
        raise ValueError("Invalid support ticket status")
    return status


def _validate_sender_type(sender_type: str) -> str:
    if sender_type not in SUPPORT_SENDER_TYPES:
        raise ValueError("Invalid support sender type")
    return sender_type


async def create_support_ticket(
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    message_text: str,
    subject: str | None = None,
):
    async with transaction() as conn:
        ticket = await conn.fetchrow(
            """
            INSERT INTO support_tickets (telegram_id, username, full_name, subject)
            VALUES ($1, $2, $3, $4)
            RETURNING id, telegram_id, username, full_name, status, assigned_admin_id,
                      subject, created_at, updated_at, closed_at
            """,
            telegram_id,
            username,
            full_name,
            subject,
        )
        await conn.fetchrow(
            """
            INSERT INTO support_messages (
                ticket_id,
                sender_type,
                sender_telegram_id,
                message_text
            )
            VALUES ($1, 'user', $2, $3)
            RETURNING id
            """,
            ticket["id"],
            telegram_id,
            message_text,
        )
        return ticket


async def add_support_message(
    ticket_id: int,
    sender_type: str,
    sender_telegram_id: int | None,
    message_text: str,
):
    _validate_sender_type(sender_type)
    async with transaction() as conn:
        message = await conn.fetchrow(
            """
            INSERT INTO support_messages (
                ticket_id,
                sender_type,
                sender_telegram_id,
                message_text
            )
            VALUES ($1, $2, $3, $4)
            RETURNING id, ticket_id, sender_type, sender_telegram_id, message_text, created_at
            """,
            ticket_id,
            sender_type,
            sender_telegram_id,
            message_text,
        )
        await conn.execute(
            """
            UPDATE support_tickets
            SET updated_at = NOW()
            WHERE id = $1
            """,
            ticket_id,
        )
        return message


async def get_ticket(ticket_id: int):
    return await fetchrow(
        """
        SELECT id, telegram_id, username, full_name, status, assigned_admin_id,
               subject, created_at, updated_at, closed_at
        FROM support_tickets
        WHERE id = $1
        LIMIT 1
        """,
        ticket_id,
    )


async def get_ticket_messages(ticket_id: int):
    return await fetch(
        """
        SELECT id, ticket_id, sender_type, sender_telegram_id, message_text, created_at
        FROM support_messages
        WHERE ticket_id = $1
        ORDER BY created_at ASC, id ASC
        """,
        ticket_id,
    )


async def get_ticket_assignments(ticket_id: int):
    return await fetch(
        """
        SELECT sa.id, sa.ticket_id, sa.admin_telegram_id, sa.assigned_by, sa.created_at,
               au.username AS admin_username,
               actor.username AS assigned_by_username
        FROM support_assignments sa
        LEFT JOIN admin_users au ON au.telegram_id = sa.admin_telegram_id
        LEFT JOIN admin_users actor ON actor.telegram_id = sa.assigned_by
        WHERE sa.ticket_id = $1
        ORDER BY sa.created_at ASC, sa.id ASC
        """,
        ticket_id,
    )


async def get_open_tickets(status: str | None = None):
    if status is not None:
        _validate_status(status)
        return await fetch(
            """
            SELECT st.id, st.telegram_id, st.username, st.full_name, st.status,
                   st.assigned_admin_id, st.subject, st.created_at, st.updated_at,
                   st.closed_at, au.username AS assigned_admin_username,
                   last_msg.message_text AS last_message_text,
                   last_msg.created_at AS last_message_at
            FROM support_tickets st
            LEFT JOIN admin_users au ON au.telegram_id = st.assigned_admin_id
            LEFT JOIN LATERAL (
                SELECT message_text, created_at
                FROM support_messages sm
                WHERE sm.ticket_id = st.id
                ORDER BY sm.created_at DESC, sm.id DESC
                LIMIT 1
            ) last_msg ON TRUE
            WHERE st.status = $1
            ORDER BY st.updated_at DESC, st.id DESC
            """,
            status,
        )

    return await fetch(
        """
        SELECT st.id, st.telegram_id, st.username, st.full_name, st.status,
               st.assigned_admin_id, st.subject, st.created_at, st.updated_at,
               st.closed_at, au.username AS assigned_admin_username,
               last_msg.message_text AS last_message_text,
               last_msg.created_at AS last_message_at
        FROM support_tickets st
        LEFT JOIN admin_users au ON au.telegram_id = st.assigned_admin_id
        LEFT JOIN LATERAL (
            SELECT message_text, created_at
            FROM support_messages sm
            WHERE sm.ticket_id = st.id
            ORDER BY sm.created_at DESC, sm.id DESC
            LIMIT 1
        ) last_msg ON TRUE
        WHERE st.status IN ('open', 'in_progress')
        ORDER BY st.updated_at DESC, st.id DESC
        """,
    )


async def list_support_tickets(status: str | None = None):
    if status == "":
        status = None
    if status is not None:
        _validate_status(status)

    if status is None:
        return await fetch(
            """
            SELECT st.id, st.telegram_id, st.username, st.full_name, st.status,
                   st.assigned_admin_id, st.subject, st.created_at, st.updated_at,
                   st.closed_at, au.username AS assigned_admin_username,
                   last_msg.message_text AS last_message_text,
                   last_msg.created_at AS last_message_at
            FROM support_tickets st
            LEFT JOIN admin_users au ON au.telegram_id = st.assigned_admin_id
            LEFT JOIN LATERAL (
                SELECT message_text, created_at
                FROM support_messages sm
                WHERE sm.ticket_id = st.id
                ORDER BY sm.created_at DESC, sm.id DESC
                LIMIT 1
            ) last_msg ON TRUE
            ORDER BY st.updated_at DESC, st.id DESC
            """,
        )

    return await fetch(
        """
        SELECT st.id, st.telegram_id, st.username, st.full_name, st.status,
               st.assigned_admin_id, st.subject, st.created_at, st.updated_at,
               st.closed_at, au.username AS assigned_admin_username,
               last_msg.message_text AS last_message_text,
               last_msg.created_at AS last_message_at
        FROM support_tickets st
        LEFT JOIN admin_users au ON au.telegram_id = st.assigned_admin_id
        LEFT JOIN LATERAL (
            SELECT message_text, created_at
            FROM support_messages sm
            WHERE sm.ticket_id = st.id
            ORDER BY sm.created_at DESC, sm.id DESC
            LIMIT 1
        ) last_msg ON TRUE
        WHERE st.status = $1
        ORDER BY st.updated_at DESC, st.id DESC
        """,
        status,
    )


async def assign_ticket(ticket_id: int, admin_telegram_id: int, assigned_by: int | None = None):
    async with transaction() as conn:
        ticket = await conn.fetchrow(
            """
            UPDATE support_tickets
            SET assigned_admin_id = $2,
                status = CASE WHEN status = 'closed' THEN status ELSE 'in_progress' END,
                updated_at = NOW()
            WHERE id = $1
            RETURNING id, telegram_id, username, full_name, status, assigned_admin_id,
                      subject, created_at, updated_at, closed_at
            """,
            ticket_id,
            admin_telegram_id,
        )
        if not ticket:
            return None

        await conn.fetchrow(
            """
            INSERT INTO support_assignments (ticket_id, admin_telegram_id, assigned_by)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            ticket_id,
            admin_telegram_id,
            assigned_by,
        )
        return ticket


async def close_ticket(ticket_id: int):
    return await fetchrow(
        """
        UPDATE support_tickets
        SET status = 'closed', closed_at = COALESCE(closed_at, NOW()), updated_at = NOW()
        WHERE id = $1
        RETURNING id, telegram_id, username, full_name, status, assigned_admin_id,
                  subject, created_at, updated_at, closed_at
        """,
        ticket_id,
    )


async def get_user_open_ticket(telegram_id: int):
    return await fetchrow(
        """
        SELECT id, telegram_id, username, full_name, status, assigned_admin_id,
               subject, created_at, updated_at, closed_at
        FROM support_tickets
        WHERE telegram_id = $1
          AND status IN ('open', 'in_progress')
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        telegram_id,
    )


async def update_ticket_status(ticket_id: int, status: str):
    _validate_status(status)
    return await fetchrow(
        """
        UPDATE support_tickets
        SET status = $2,
            closed_at = CASE WHEN $2 = 'closed' THEN COALESCE(closed_at, NOW()) ELSE NULL END,
            updated_at = NOW()
        WHERE id = $1
        RETURNING id, telegram_id, username, full_name, status, assigned_admin_id,
                  subject, created_at, updated_at, closed_at
        """,
        ticket_id,
        status,
    )
