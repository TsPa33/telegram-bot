CREATE TABLE IF NOT EXISTS buyer_leads (
    id SERIAL PRIMARY KEY,
    name TEXT,
    phone TEXT,
    query TEXT,
    city TEXT,
    source TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_buyer_leads_created_at ON buyer_leads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_buyer_leads_city ON buyer_leads(city);
