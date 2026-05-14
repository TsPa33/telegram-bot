CREATE TABLE IF NOT EXISTS buyer_favorites (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('car', 'seller', 'service', 'website')),
    entity_ref TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (telegram_id, entity_type, entity_ref)
);

CREATE TABLE IF NOT EXISTS buyer_requests (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    request_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_ref TEXT NOT NULL,
    seller_id INTEGER NULL REFERENCES sellers(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'viewed', 'answered', 'closed')),
    message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS buyer_garage (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    vehicle_name TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS buyer_history (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('car', 'seller', 'service')),
    entity_ref TEXT NOT NULL,
    viewed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (telegram_id, entity_type, entity_ref)
);

CREATE INDEX IF NOT EXISTS idx_buyer_favorites_user_created ON buyer_favorites(telegram_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_buyer_favorites_entity ON buyer_favorites(entity_type, entity_ref);
CREATE INDEX IF NOT EXISTS idx_buyer_requests_user_created ON buyer_requests(telegram_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_buyer_requests_status ON buyer_requests(status);
CREATE INDEX IF NOT EXISTS idx_buyer_requests_seller ON buyer_requests(seller_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_buyer_garage_user_vehicle_lower ON buyer_garage(telegram_id, lower(vehicle_name));
CREATE INDEX IF NOT EXISTS idx_buyer_garage_user_updated ON buyer_garage(telegram_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_buyer_history_user_viewed ON buyer_history(telegram_id, viewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_buyer_history_entity ON buyer_history(entity_type, entity_ref);
