CREATE TABLE IF NOT EXISTS part_templates (
    id BIGSERIAL PRIMARY KEY,
    vehicle_type TEXT NOT NULL DEFAULT 'passenger',
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(vehicle_type, category, name)
);

CREATE TABLE IF NOT EXISTS seller_parts (
    id BIGSERIAL PRIMARY KEY,
    seller_id BIGINT NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
    car_id BIGINT NOT NULL REFERENCES seller_cars(id) ON DELETE CASCADE,
    template_id BIGINT REFERENCES part_templates(id) ON DELETE SET NULL,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    price NUMERIC(12,2),
    photo_id TEXT,
    description TEXT,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(car_id, name)
);

CREATE INDEX IF NOT EXISTS idx_seller_parts_seller_id ON seller_parts(seller_id);
CREATE INDEX IF NOT EXISTS idx_seller_parts_car_id ON seller_parts(car_id);
CREATE INDEX IF NOT EXISTS idx_seller_parts_status ON seller_parts(status);
CREATE INDEX IF NOT EXISTS idx_seller_parts_category ON seller_parts(category);
CREATE INDEX IF NOT EXISTS idx_seller_parts_name ON seller_parts(name);
CREATE INDEX IF NOT EXISTS idx_seller_parts_seller_status ON seller_parts(seller_id, status);
CREATE INDEX IF NOT EXISTS idx_seller_parts_car_status ON seller_parts(car_id, status);

CREATE INDEX IF NOT EXISTS idx_seller_parts_updated_at ON seller_parts(updated_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'seller_parts_status_check'
    ) THEN
        ALTER TABLE seller_parts
        ADD CONSTRAINT seller_parts_status_check
        CHECK (status IN ('draft', 'available', 'sold', 'hidden'));
    END IF;
END $$;


INSERT INTO part_templates (vehicle_type, category, name, sort_order, is_active)
VALUES
('passenger','Body','Hood',1,TRUE),('passenger','Body','Front bumper',2,TRUE),('passenger','Body','Rear bumper',3,TRUE),('passenger','Body','Front left fender',4,TRUE),('passenger','Body','Front right fender',5,TRUE),('passenger','Body','Front left door',6,TRUE),('passenger','Body','Front right door',7,TRUE),('passenger','Body','Rear left door',8,TRUE),('passenger','Body','Rear right door',9,TRUE),('passenger','Body','Trunk lid',10,TRUE),('passenger','Body','Tailgate',11,TRUE),('passenger','Body','Roof',12,TRUE),('passenger','Body','Left side skirt',13,TRUE),('passenger','Body','Right side skirt',14,TRUE),('passenger','Body','Left wheel arch liner',15,TRUE),('passenger','Body','Right wheel arch liner',16,TRUE),('passenger','Body','Front panel',17,TRUE),('passenger','Body','Radiator support',18,TRUE),('passenger','Body','Bumper reinforcement',19,TRUE),('passenger','Body','Hood lock',20,TRUE),
('passenger','Optics','Left headlight',1,TRUE),('passenger','Optics','Right headlight',2,TRUE),('passenger','Optics','Left tail light',3,TRUE),('passenger','Optics','Right tail light',4,TRUE),('passenger','Optics','Left fog light',5,TRUE),('passenger','Optics','Right fog light',6,TRUE),('passenger','Optics','Left turn signal',7,TRUE),('passenger','Optics','Right turn signal',8,TRUE),('passenger','Optics','Left trunk light',9,TRUE),('passenger','Optics','Right trunk light',10,TRUE),
('passenger','Engine','Complete engine',1,TRUE),('passenger','Engine','Engine block',2,TRUE),('passenger','Engine','Cylinder head',3,TRUE),('passenger','Engine','Turbocharger',4,TRUE),('passenger','Engine','Injector',5,TRUE),('passenger','Engine','High-pressure fuel pump',6,TRUE),('passenger','Engine','Starter',7,TRUE),('passenger','Engine','Alternator',8,TRUE),('passenger','Engine','Throttle body',9,TRUE),('passenger','Engine','Intake manifold',10,TRUE),('passenger','Engine','Exhaust manifold',11,TRUE),('passenger','Engine','EGR valve',12,TRUE),('passenger','Engine','Flywheel',13,TRUE),('passenger','Engine','Engine mount',14,TRUE),('passenger','Engine','AC compressor',15,TRUE),
('passenger','Transmission','Manual gearbox',1,TRUE),('passenger','Transmission','Automatic gearbox',2,TRUE),('passenger','Transmission','Clutch',3,TRUE),('passenger','Transmission','Torque converter',4,TRUE),('passenger','Transmission','Left drive shaft',5,TRUE),('passenger','Transmission','Right drive shaft',6,TRUE),('passenger','Transmission','Driveshaft',7,TRUE),('passenger','Transmission','Differential',8,TRUE),('passenger','Transmission','Axle shaft',9,TRUE),('passenger','Transmission','Gear shifter assembly',10,TRUE),
('passenger','Suspension','Front left shock absorber',1,TRUE),('passenger','Suspension','Front right shock absorber',2,TRUE),('passenger','Suspension','Rear left shock absorber',3,TRUE),('passenger','Suspension','Rear right shock absorber',4,TRUE),('passenger','Suspension','Front spring',5,TRUE),('passenger','Suspension','Rear spring',6,TRUE),('passenger','Suspension','Front left control arm',7,TRUE),('passenger','Suspension','Front right control arm',8,TRUE),('passenger','Suspension','Rear axle beam',9,TRUE),('passenger','Suspension','Front subframe',10,TRUE),('passenger','Suspension','Rear subframe',11,TRUE),('passenger','Suspension','Stabilizer bar',12,TRUE),('passenger','Suspension','Front left hub',13,TRUE),('passenger','Suspension','Front right hub',14,TRUE),('passenger','Suspension','Rear left hub',15,TRUE),('passenger','Suspension','Rear right hub',16,TRUE),
('passenger','Brakes','Front left brake caliper',1,TRUE),('passenger','Brakes','Front right brake caliper',2,TRUE),('passenger','Brakes','Rear left brake caliper',3,TRUE),('passenger','Brakes','Rear right brake caliper',4,TRUE),('passenger','Brakes','Brake master cylinder',5,TRUE),('passenger','Brakes','Brake booster',6,TRUE),('passenger','Brakes','ABS module',7,TRUE),('passenger','Brakes','Front brake disc',8,TRUE),('passenger','Brakes','Rear brake disc',9,TRUE),
('passenger','Interior','Driver seat',1,TRUE),('passenger','Interior','Passenger seat',2,TRUE),('passenger','Interior','Rear bench seat',3,TRUE),('passenger','Interior','Left door card',4,TRUE),('passenger','Interior','Right door card',5,TRUE),('passenger','Interior','Steering wheel',6,TRUE),('passenger','Interior','Instrument cluster',7,TRUE),('passenger','Interior','Dashboard',8,TRUE),('passenger','Interior','Glove box',9,TRUE),('passenger','Interior','Center console',10,TRUE),('passenger','Interior','Radio unit',11,TRUE),('passenger','Interior','Climate control unit',12,TRUE),('passenger','Interior','Seat belt',13,TRUE),('passenger','Interior','Driver airbag',14,TRUE),('passenger','Interior','Passenger airbag',15,TRUE),
('passenger','Electrical','Engine ECU',1,TRUE),('passenger','Electrical','Comfort control module',2,TRUE),('passenger','Electrical','Fuse box',3,TRUE),('passenger','Electrical','Engine wiring harness',4,TRUE),('passenger','Electrical','Interior wiring harness',5,TRUE),('passenger','Electrical','ABS sensor',6,TRUE),('passenger','Electrical','Crankshaft sensor',7,TRUE),('passenger','Electrical','Camshaft sensor',8,TRUE),('passenger','Electrical','Fuel pressure sensor',9,TRUE),('passenger','Electrical','Parking sensor',10,TRUE),('passenger','Electrical','Ignition switch',11,TRUE),('passenger','Electrical','Key',12,TRUE),('passenger','Electrical','Instrument cluster',13,TRUE),('passenger','Electrical','Left window regulator',14,TRUE),('passenger','Electrical','Right window regulator',15,TRUE),
('passenger','Cooling / AC','Main radiator',1,TRUE),('passenger','Cooling / AC','AC condenser',2,TRUE),('passenger','Cooling / AC','Intercooler',3,TRUE),('passenger','Cooling / AC','Radiator fan',4,TRUE),('passenger','Cooling / AC','Coolant hose',5,TRUE),('passenger','Cooling / AC','Thermostat',6,TRUE),('passenger','Cooling / AC','Expansion tank',7,TRUE),('passenger','Cooling / AC','Heater core',8,TRUE),('passenger','Cooling / AC','Heater blower motor',9,TRUE),
('passenger','Mirrors / Glass','Left mirror',1,TRUE),('passenger','Mirrors / Glass','Right mirror',2,TRUE),('passenger','Mirrors / Glass','Windshield',3,TRUE),('passenger','Mirrors / Glass','Rear window',4,TRUE),('passenger','Mirrors / Glass','Front left door glass',5,TRUE),('passenger','Mirrors / Glass','Front right door glass',6,TRUE),('passenger','Mirrors / Glass','Rear left door glass',7,TRUE),('passenger','Mirrors / Glass','Rear right door glass',8,TRUE)
ON CONFLICT (vehicle_type, category, name) DO NOTHING;
