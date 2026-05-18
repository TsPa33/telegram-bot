CREATE TABLE IF NOT EXISTS seller_products (
    id SERIAL PRIMARY KEY,
    seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    donor_car_id INTEGER NULL REFERENCES seller_cars(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    brand TEXT NULL,
    model TEXT NULL,
    oem_code TEXT NULL,
    condition TEXT NULL,
    description TEXT NULL,
    price NUMERIC(12,2) NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    stock_status TEXT NOT NULL DEFAULT 'available'
        CHECK (stock_status IN ('available', 'low_stock', 'sold', 'preorder')),
    photo_url TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'archived')),
    views INTEGER NOT NULL DEFAULT 0,
    phone_clicks INTEGER NOT NULL DEFAULT 0,
    site_clicks INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seller_products_seller_id
    ON seller_products (seller_id);

CREATE INDEX IF NOT EXISTS idx_seller_products_donor_car_id
    ON seller_products (donor_car_id);

CREATE INDEX IF NOT EXISTS idx_seller_products_category
    ON seller_products (category);

CREATE INDEX IF NOT EXISTS idx_seller_products_status
    ON seller_products (status);

CREATE INDEX IF NOT EXISTS idx_seller_products_title
    ON seller_products (title);

CREATE INDEX IF NOT EXISTS idx_seller_products_oem_code
    ON seller_products (oem_code);
