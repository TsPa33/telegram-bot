ALTER TABLE buyer_request_offers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS marketplace_status TEXT NOT NULL DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_buyer_request_offers_status_request
    ON buyer_request_offers(request_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS marketplace_matches (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES buyer_requests(id) ON DELETE CASCADE,
    offer_id INTEGER NOT NULL REFERENCES buyer_request_offers(id) ON DELETE CASCADE,
    seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'matched' CHECK (status IN ('matched', 'contacted', 'closed', 'cancelled')),
    matched_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (request_id)
);

CREATE INDEX IF NOT EXISTS idx_marketplace_matches_seller_status
    ON marketplace_matches(seller_id, status, matched_at DESC);
CREATE INDEX IF NOT EXISTS idx_marketplace_matches_offer
    ON marketplace_matches(offer_id);

CREATE TABLE IF NOT EXISTS marketplace_notification_events (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    request_id INTEGER REFERENCES buyer_requests(id) ON DELETE CASCADE,
    offer_id INTEGER REFERENCES buyer_request_offers(id) ON DELETE CASCADE,
    seller_id INTEGER REFERENCES sellers(id) ON DELETE CASCADE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed', 'cancelled')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_marketplace_notification_events_status
    ON marketplace_notification_events(status, created_at);
CREATE INDEX IF NOT EXISTS idx_marketplace_notification_events_seller
    ON marketplace_notification_events(seller_id, created_at DESC);
