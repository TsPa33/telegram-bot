ALTER TABLE payments ADD COLUMN IF NOT EXISTS product_type TEXT NOT NULL DEFAULT 'garage';

UPDATE payments
SET product_type = product
WHERE product IS NOT NULL
  AND product_type = 'garage'
  AND product <> 'garage';

ALTER TABLE sellers ADD COLUMN IF NOT EXISTS crm_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS seller_crm_subscriptions (
    id SERIAL PRIMARY KEY,
    seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    payment_id INTEGER UNIQUE REFERENCES payments(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'cancelled')),
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seller_crm_subscriptions_seller_id
    ON seller_crm_subscriptions (seller_id);

CREATE INDEX IF NOT EXISTS idx_seller_crm_subscriptions_status_expires
    ON seller_crm_subscriptions (status, expires_at);

CREATE TABLE IF NOT EXISTS seller_crm_accounts (
    id SERIAL PRIMARY KEY,
    seller_id INTEGER NOT NULL UNIQUE REFERENCES sellers(id) ON DELETE CASCADE,
    crm_slug TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seller_crm_accounts_seller_id
    ON seller_crm_accounts (seller_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_seller_crm_accounts_slug_lower
    ON seller_crm_accounts (lower(crm_slug));

CREATE TABLE IF NOT EXISTS seller_crm_sessions (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES seller_crm_accounts(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_seller_crm_sessions_account_id
    ON seller_crm_sessions (account_id);

CREATE INDEX IF NOT EXISTS idx_seller_crm_sessions_expires_at
    ON seller_crm_sessions (expires_at);
