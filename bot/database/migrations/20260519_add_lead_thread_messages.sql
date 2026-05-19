CREATE TABLE IF NOT EXISTS lead_thread_messages (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES buyer_requests(id) ON DELETE CASCADE,
    proposal_id INTEGER NULL REFERENCES buyer_request_offers(id) ON DELETE SET NULL,
    sender_role TEXT NOT NULL CHECK (sender_role IN ('buyer', 'seller', 'system')),
    sender_id TEXT,
    message_text TEXT NOT NULL,
    read_state TEXT NOT NULL DEFAULT 'unread' CHECK (read_state IN ('unread', 'read')),
    telegram_chat_id BIGINT,
    telegram_message_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lead_thread_messages_lead_created
    ON lead_thread_messages(lead_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_lead_thread_messages_proposal_created
    ON lead_thread_messages(proposal_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_lead_thread_messages_telegram_reply
    ON lead_thread_messages(telegram_chat_id, telegram_message_id);
