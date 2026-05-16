ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS request_fingerprint TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS normalized_phone TEXT;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS safety_status TEXT NOT NULL DEFAULT 'clear';
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS safety_flags JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE buyer_requests ADD COLUMN IF NOT EXISTS photo_pipeline_status TEXT NOT NULL DEFAULT 'metadata_only';

CREATE INDEX IF NOT EXISTS idx_buyer_requests_fingerprint ON buyer_requests(request_fingerprint);
CREATE INDEX IF NOT EXISTS idx_buyer_requests_safety_status ON buyer_requests(safety_status, created_at DESC);

ALTER TABLE buyer_request_offers ADD COLUMN IF NOT EXISTS availability_note TEXT;
ALTER TABLE buyer_request_offers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS seller_lead_actions (
    id SERIAL PRIMARY KEY,
    seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    request_id INTEGER NOT NULL REFERENCES buyer_requests(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('viewed', 'skipped', 'offered', 'declined')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (seller_id, request_id, action)
);

CREATE INDEX IF NOT EXISTS idx_seller_lead_actions_seller_action ON seller_lead_actions(seller_id, action, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_seller_lead_actions_request ON seller_lead_actions(request_id, updated_at DESC);
