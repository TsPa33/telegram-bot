CREATE TABLE IF NOT EXISTS buyer_leads (
    id SERIAL PRIMARY KEY,
    what_needed TEXT NOT NULL,
    phone TEXT NOT NULL,
    city TEXT,
    telegram TEXT,
    vin TEXT,
    description TEXT,
    photos TEXT,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'matched', 'answered', 'closed', 'rejected')),
    source_path TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_buyer_leads_status ON buyer_leads(status);
CREATE INDEX IF NOT EXISTS idx_buyer_leads_city ON buyer_leads(city);
CREATE INDEX IF NOT EXISTS idx_buyer_leads_created_at ON buyer_leads(created_at DESC);
