-- Keep oldest record per (car_id, lower(name)); remove newer duplicates safely.
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY car_id, LOWER(name)
            ORDER BY id ASC
        ) AS rn
    FROM seller_parts
)
DELETE FROM seller_parts sp
USING ranked r
WHERE sp.id = r.id
  AND r.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_part_name_per_car
ON seller_parts (car_id, LOWER(name));
