from bot.database.base import execute, fetch, fetchrow

LEAD_THREAD_SENDER_BUYER = "buyer"
LEAD_THREAD_SENDER_SELLER = "seller"
LEAD_THREAD_READ_UNREAD = "unread"
LEAD_THREAD_READ_READ = "read"


def _clean_message_text(text: str | None, *, limit: int = 2000) -> str:
    return (text or "").strip()[:limit]


async def create_lead_thread_message(
    *,
    lead_id: int,
    proposal_id: int | None = None,
    sender_role: str,
    sender_id: str | int | None,
    message_text: str,
    read_state: str = LEAD_THREAD_READ_UNREAD,
    telegram_chat_id: int | None = None,
    telegram_message_id: int | None = None,
):
    cleaned = _clean_message_text(message_text)
    if not cleaned:
        return None
    return await fetchrow(
        """
        INSERT INTO lead_thread_messages (
            lead_id, proposal_id, sender_role, sender_id, message_text, read_state,
            telegram_chat_id, telegram_message_id, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        RETURNING id, lead_id, proposal_id, sender_role, sender_id, message_text, read_state,
                  telegram_chat_id, telegram_message_id, created_at
        """,
        lead_id,
        proposal_id,
        sender_role,
        str(sender_id) if sender_id is not None else None,
        cleaned,
        read_state,
        telegram_chat_id,
        telegram_message_id,
    )


async def attach_telegram_delivery_to_thread_message(
    *,
    message_id: int,
    telegram_chat_id: int,
    telegram_message_id: int,
):
    return await fetchrow(
        """
        UPDATE lead_thread_messages
        SET telegram_chat_id = $2, telegram_message_id = $3
        WHERE id = $1
        RETURNING id, lead_id, proposal_id, sender_role, sender_id, message_text, read_state,
                  telegram_chat_id, telegram_message_id, created_at
        """,
        message_id,
        telegram_chat_id,
        telegram_message_id,
    )


async def get_thread_context_by_telegram_reply(*, telegram_chat_id: int, telegram_message_id: int):
    row = await fetchrow(
        """
        SELECT ltm.id AS thread_message_id,
               ltm.lead_id,
               ltm.proposal_id,
               ltm.sender_role,
               ltm.sender_id,
               COALESCE(bro.seller_id, CASE WHEN ltm.sender_role = 'seller' AND ltm.sender_id ~ '^[0-9]+$' THEN ltm.sender_id::int ELSE NULL END) AS seller_id,
               br.telegram_id AS buyer_telegram_id,
               br.buyer_telegram
        FROM lead_thread_messages ltm
        JOIN buyer_requests br ON br.id = ltm.lead_id
        LEFT JOIN buyer_request_offers bro ON bro.id = ltm.proposal_id
        WHERE ltm.telegram_chat_id = $1
          AND ltm.telegram_message_id = $2
          AND br.entity_type = 'marketplace_request'
        LIMIT 1
        """,
        telegram_chat_id,
        telegram_message_id,
    )
    return dict(row) if row else None


async def list_lead_thread_messages(*, lead_id: int, seller_id: int | None = None, proposal_id: int | None = None):
    return await fetch(
        """
        SELECT ltm.id, ltm.lead_id, ltm.proposal_id, ltm.sender_role, ltm.sender_id,
               ltm.message_text, ltm.read_state, ltm.created_at,
               bro.seller_id,
               CASE
                   WHEN ltm.sender_role = 'buyer' THEN COALESCE(NULLIF(br.buyer_name, ''), 'Покупець')
                   WHEN ltm.sender_role = 'seller' THEN COALESCE(NULLIF(s.shop_name, ''), NULLIF(s.name, ''), 'Продавець')
                   ELSE 'CarPot'
               END AS sender_label
        FROM lead_thread_messages ltm
        JOIN buyer_requests br ON br.id = ltm.lead_id
        LEFT JOIN buyer_request_offers bro ON bro.id = ltm.proposal_id
        LEFT JOIN sellers s ON s.id = COALESCE(bro.seller_id, CASE WHEN ltm.sender_role = 'seller' AND ltm.sender_id ~ '^[0-9]+$' THEN ltm.sender_id::int ELSE NULL END)
        WHERE ltm.lead_id = $1
          AND ($2::int IS NULL OR bro.seller_id = $2 OR (ltm.proposal_id IS NULL AND ltm.sender_role = 'buyer') OR (ltm.sender_role = 'seller' AND ltm.sender_id = $2::text))
          AND ($3::int IS NULL OR ltm.proposal_id = $3 OR ltm.proposal_id IS NULL)
        ORDER BY ltm.created_at ASC, ltm.id ASC
        """,
        lead_id,
        seller_id,
        proposal_id,
    )


async def mark_lead_thread_messages_read(*, lead_id: int, reader_role: str, seller_id: int | None = None):
    await execute(
        """
        UPDATE lead_thread_messages ltm
        SET read_state = 'read'
        FROM buyer_request_offers bro
        WHERE ltm.lead_id = $1
          AND ltm.sender_role <> $2
          AND (ltm.proposal_id = bro.id OR ltm.proposal_id IS NULL)
          AND ($3::int IS NULL OR bro.seller_id = $3 OR ltm.proposal_id IS NULL)
        """,
        lead_id,
        reader_role,
        seller_id,
    )


async def get_seller_thread_notification_context(*, lead_id: int, proposal_id: int | None = None, seller_id: int | None = None):
    row = await fetchrow(
        """
        SELECT br.id AS lead_id, br.brand, br.model, br.category, br.description,
               bro.id AS proposal_id,
               COALESCE(bro.seller_id, $3::int) AS seller_id,
               s.telegram_id AS seller_telegram_id,
               s.shop_name, s.name AS seller_name
        FROM buyer_requests br
        LEFT JOIN buyer_request_offers bro
          ON bro.request_id = br.id
         AND ($2::int IS NULL OR bro.id = $2)
         AND ($3::int IS NULL OR bro.seller_id = $3)
        LEFT JOIN sellers s ON s.id = COALESCE(bro.seller_id, $3::int)
        WHERE br.id = $1
          AND br.entity_type = 'marketplace_request'
        ORDER BY bro.updated_at DESC NULLS LAST, bro.id DESC NULLS LAST
        LIMIT 1
        """,
        lead_id,
        proposal_id,
        seller_id,
    )
    return dict(row) if row else None


async def get_buyer_thread_delivery_context(*, lead_id: int, seller_id: int, proposal_id: int | None = None):
    row = await fetchrow(
        """
        SELECT br.id AS lead_id, br.telegram_id AS buyer_telegram_id, br.buyer_telegram,
               br.brand, br.model, br.category, br.description,
               bro.id AS proposal_id,
               s.shop_name, s.name AS seller_name
        FROM buyer_requests br
        LEFT JOIN buyer_request_offers bro
          ON bro.request_id = br.id
         AND bro.seller_id = $2
         AND ($3::int IS NULL OR bro.id = $3)
        JOIN sellers s ON s.id = $2
        WHERE br.id = $1
          AND br.entity_type = 'marketplace_request'
        ORDER BY bro.updated_at DESC NULLS LAST, bro.id DESC NULLS LAST
        LIMIT 1
        """,
        lead_id,
        seller_id,
        proposal_id,
    )
    return dict(row) if row else None
