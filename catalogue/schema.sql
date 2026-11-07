-- Isolated catalogue-staging ONLY; non-destructive, idempotent.
CREATE TABLE IF NOT EXISTS catalogue_parts (
 supplier_id SMALLINT UNSIGNED NOT NULL,
 article_number VARCHAR(32) NOT NULL,
 name_source VARCHAR(128) NULL,
 name_uk VARCHAR(128) NULL,
 PRIMARY KEY (supplier_id, article_number),
 INDEX idx_article_number (article_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS catalogue_oem (
 supplier_id SMALLINT UNSIGNED NOT NULL,
 article_number VARCHAR(32) NOT NULL,
 oem_manufacturer_id INT UNSIGNED NOT NULL,
 oem_number VARCHAR(64) NOT NULL,
 PRIMARY KEY (supplier_id, article_number, oem_manufacturer_id, oem_number),
 INDEX idx_oem_number (oem_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS catalogue_manufacturers (
 id INT UNSIGNED NOT NULL PRIMARY KEY,
 name_source VARCHAR(128) NULL,
 full_name_source VARCHAR(128) NULL,
 name_uk VARCHAR(128) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS catalogue_models (
 id INT UNSIGNED NOT NULL PRIMARY KEY,
 manufacturer_id INT UNSIGNED NOT NULL,
 name_source VARCHAR(128) NULL,
 production_interval VARCHAR(64) NULL,
 name_uk VARCHAR(128) NULL,
 INDEX idx_model_manufacturer (manufacturer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Existing compact catalogue tables are retained. Staging-only additive migration.
CREATE TABLE IF NOT EXISTS catalogue_import_progress (
  job VARCHAR(32) NOT NULL PRIMARY KEY,
  last_supplier_id SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  last_article_number VARCHAR(32) NOT NULL DEFAULT '',
  last_manufacturer_id INT UNSIGNED NOT NULL DEFAULT 0,
  last_oem_number VARCHAR(64) NOT NULL DEFAULT '',
  processed BIGINT UNSIGNED NOT NULL DEFAULT 0,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
