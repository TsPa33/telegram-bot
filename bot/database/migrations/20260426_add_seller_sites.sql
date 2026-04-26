BEGIN;

CREATE TABLE IF NOT EXISTS seller_sites (
    id BIGSERIAL PRIMARY KEY,
    seller_id BIGINT NOT NULL UNIQUE REFERENCES sellers(id) ON DELETE CASCADE,
    subdomain TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'draft',
    config_draft JSONB NOT NULL DEFAULT '{}'::jsonb,
    config_live JSONB NOT NULL DEFAULT '{}'::jsonb,
    has_custom_domain BOOLEAN NOT NULL DEFAULT FALSE,
    custom_domain TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seller_sites_subdomain
    ON seller_sites (subdomain);

CREATE INDEX IF NOT EXISTS idx_seller_sites_seller_id
    ON seller_sites (seller_id);

CREATE OR REPLACE FUNCTION set_seller_sites_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_seller_sites_set_updated_at'
          AND tgrelid = 'seller_sites'::regclass
    ) THEN
        CREATE TRIGGER trg_seller_sites_set_updated_at
        BEFORE UPDATE ON seller_sites
        FOR EACH ROW
        EXECUTE FUNCTION set_seller_sites_updated_at();
    END IF;
END;
$$;

COMMIT;
