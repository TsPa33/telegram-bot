-- Additive, catalogue-staging only. Apply explicitly after review; never on API startup.
CREATE TABLE IF NOT EXISTS catalogue_volvo_snapshots (
 car_id INT UNSIGNED NOT NULL PRIMARY KEY,
 model_id INT UNSIGNED NOT NULL,
 payload JSON NOT NULL,
 sha256 CHAR(64) NOT NULL,
 coverage VARCHAR(24) NOT NULL DEFAULT 'partial',
 observed_at TIMESTAMP NOT NULL,
 INDEX idx_volvo_model (model_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS catalogue_suppliers (
 supplier_id INT UNSIGNED NOT NULL PRIMARY KEY,
 name_source VARCHAR(128) NOT NULL,
 observed_at TIMESTAMP NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Immutable raw export versions; latest directory stores only a compact projection.
CREATE TABLE IF NOT EXISTS catalogue_volvo_versions (
 car_id INT UNSIGNED NOT NULL,
 sha256 CHAR(64) NOT NULL,
 payload JSON NOT NULL,
 coverage VARCHAR(24) NOT NULL,
 observed_at TIMESTAMP NOT NULL,
 PRIMARY KEY (car_id, sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
