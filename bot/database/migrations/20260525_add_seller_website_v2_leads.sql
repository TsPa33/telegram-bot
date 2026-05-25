CREATE TABLE IF NOT EXISTS seller_website_v2_leads (
    id BIGSERIAL PRIMARY KEY,
    website_id BIGINT NOT NULL REFERENCES seller_websites_v2(id) ON DELETE CASCADE,
    seller_id BIGINT NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    lead_type TEXT NOT NULL DEFAULT 'contact',
    name TEXT,
    phone TEXT NOT NULL,
    message TEXT,
    vin TEXT,
    item_title TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seller_website_v2_leads_website_id ON seller_website_v2_leads (website_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_seller_website_v2_leads_seller_id ON seller_website_v2_leads (seller_id, created_at DESC);
