-- Apply only to the isolated catalogue-staging MySQL database.
-- No changes to existing local source or Warehouse tables.
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
