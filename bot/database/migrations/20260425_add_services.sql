CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    seller_id BIGINT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    city TEXT NOT NULL,
    address TEXT NOT NULL,
    description TEXT,
    website TEXT,
    photo_id TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE service_stats (
    service_id INT PRIMARY KEY,
    views INT DEFAULT 0,
    calls INT DEFAULT 0,
    clicks INT DEFAULT 0
);
