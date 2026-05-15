CREATE TABLE IF NOT EXISTS buyer_requests (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL DEFAULT 0,
    request_type TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'marketplace_request',
    entity_ref TEXT NOT NULL DEFAULT 'web-marketplace',
    seller_id INTEGER NULL REFERENCES sellers(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'new',
    message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS buyer_name TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS buyer_phone TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS buyer_telegram TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS brand TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS model TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS vin TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS photos JSONB DEFAULT '[]'::jsonb;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS urgency TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS marketplace_status TEXT NOT NULL DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_buyer_requests_marketplace_status ON buyer_requests(marketplace_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_buyer_requests_city_category ON buyer_requests(city, category);

CREATE TABLE IF NOT EXISTS buyer_request_offers (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES buyer_requests(id) ON DELETE CASCADE,
    seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    price_offer NUMERIC(12,2),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_buyer_request_offers_request ON buyer_request_offers(request_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_buyer_request_offers_seller ON buyer_request_offers(seller_id, created_at DESC);
