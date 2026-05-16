ALTER TABLE seller_cars ADD COLUMN IF NOT EXISTS inventory_kind TEXT NOT NULL DEFAULT 'donor_vehicle';
ALTER TABLE seller_cars ADD COLUMN IF NOT EXISTS donor_generation TEXT;
ALTER TABLE seller_cars ADD COLUMN IF NOT EXISTS engine_code TEXT;
ALTER TABLE seller_cars ADD COLUMN IF NOT EXISTS engine_family TEXT;
ALTER TABLE seller_cars ADD COLUMN IF NOT EXISTS fuel_type TEXT;
ALTER TABLE seller_cars ADD COLUMN IF NOT EXISTS transmission_type TEXT;
ALTER TABLE seller_cars ADD COLUMN IF NOT EXISTS compatibility_notes TEXT;
ALTER TABLE sellers ADD COLUMN IF NOT EXISTS specialization_tags TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_seller_cars_inventory_kind ON seller_cars(inventory_kind);
CREATE INDEX IF NOT EXISTS idx_seller_cars_donor_generation ON seller_cars(donor_generation);
CREATE INDEX IF NOT EXISTS idx_seller_cars_engine_code ON seller_cars(engine_code);
CREATE INDEX IF NOT EXISTS idx_seller_cars_fuel_type ON seller_cars(fuel_type);
CREATE INDEX IF NOT EXISTS idx_seller_cars_transmission_type ON seller_cars(transmission_type);
CREATE INDEX IF NOT EXISTS idx_sellers_specialization_tags ON sellers USING GIN (specialization_tags);
