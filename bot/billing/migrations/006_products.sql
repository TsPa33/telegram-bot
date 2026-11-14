-- Additive product terms; financial records remain in the existing canonical tables.
CREATE TABLE billing.product_terms (
 sku text NOT NULL, version integer NOT NULL,
 cadence text NOT NULL CHECK(cadence IN ('days30','year','perpetual')),
 source text NOT NULL, PRIMARY KEY(sku,version),
 FOREIGN KEY(sku,version) REFERENCES billing.plan_versions
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.product_terms FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.product_terms FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
CREATE TABLE billing.legacy_mappings (
 peer text NOT NULL, legacy_order text NOT NULL, invoice_id text NOT NULL UNIQUE REFERENCES billing.invoices,
 settlement_id text NOT NULL UNIQUE REFERENCES billing.settlements,
 evidence_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(peer,legacy_order)
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.legacy_mappings FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.legacy_mappings FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
