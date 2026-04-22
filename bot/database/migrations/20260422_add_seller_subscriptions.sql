CREATE TABLE IF NOT EXISTS seller_subscriptions (
    id SERIAL PRIMARY KEY,
    seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    slots INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    payment_id INTEGER REFERENCES payments(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_seller_subscriptions_seller_id
    ON seller_subscriptions (seller_id);

CREATE INDEX IF NOT EXISTS idx_seller_subscriptions_expires_at
    ON seller_subscriptions (expires_at);
