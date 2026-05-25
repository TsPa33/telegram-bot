CREATE TABLE IF NOT EXISTS seller_websites_v2 (
    id BIGSERIAL PRIMARY KEY,
    seller_id BIGINT NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    site_type TEXT NOT NULL,
    name TEXT NOT NULL,
    subdomain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    config_draft JSONB NOT NULL DEFAULT '{}'::jsonb,
    config_live JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    published_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_seller_websites_v2_subdomain_unique ON seller_websites_v2 ((lower(trim(subdomain))));
CREATE INDEX IF NOT EXISTS idx_seller_websites_v2_seller ON seller_websites_v2 (seller_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'seller_websites_v2_site_type_check') THEN
        ALTER TABLE seller_websites_v2
            ADD CONSTRAINT seller_websites_v2_site_type_check
            CHECK (site_type IN ('carpot_catalog', 'carpot_business'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'seller_websites_v2_status_check') THEN
        ALTER TABLE seller_websites_v2
            ADD CONSTRAINT seller_websites_v2_status_check
            CHECK (status IN ('draft', 'published', 'suspended', 'expired'));
    END IF;
END $$;
