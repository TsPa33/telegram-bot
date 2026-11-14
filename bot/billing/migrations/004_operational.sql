-- Additive operational extension. Existing fixture/sandbox evidence is preserved.
CREATE TABLE billing.operational_identity(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), environment text NOT NULL CHECK(environment IN ('sandbox','production')));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.operational_identity FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.operational_identity FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
ALTER TABLE billing.intents DROP CONSTRAINT intents_provider_check;
ALTER TABLE billing.intents DROP CONSTRAINT intents_environment_check;
ALTER TABLE billing.intents DROP CONSTRAINT intents_merchant_check;
ALTER TABLE billing.intents ADD CHECK((provider='fixture' AND environment='test' AND merchant='disposable-fixture') OR (provider='liqpay' AND environment IN ('sandbox','production') AND length(merchant)>0));
CREATE TABLE billing.provider_orders(
 order_id text PRIMARY KEY, intent_id text NOT NULL UNIQUE REFERENCES billing.intents,
 profile text NOT NULL, result_url text NOT NULL, server_url text NOT NULL,
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.provider_orders FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.provider_orders FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
CREATE TABLE billing.provider_evidence(
 provider text NOT NULL, environment text NOT NULL, digest text NOT NULL,
 order_id text NOT NULL REFERENCES billing.provider_orders, payment_id text,
 status text NOT NULL, classification text NOT NULL, source text NOT NULL CHECK(source IN ('callback','status')),
 received_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(provider,environment,digest));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.provider_evidence FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.provider_evidence FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
CREATE TABLE billing.provider_transactions(
 provider text NOT NULL, environment text NOT NULL, merchant text NOT NULL, payment_id text NOT NULL,
 intent_id text NOT NULL REFERENCES billing.intents, PRIMARY KEY(provider,environment,merchant,payment_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.provider_transactions FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.provider_transactions FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
ALTER TABLE billing.outbox DROP CONSTRAINT outbox_topic_check;
ALTER TABLE billing.outbox ADD CHECK(topic IN ('billing.entitlement.snapshot.v1','billing.entitlement.snapshot.v2'));
CREATE TABLE billing.outbox_delivery(
 outbox_id text PRIMARY KEY REFERENCES billing.outbox, attempts integer NOT NULL DEFAULT 0,
 next_attempt_at timestamptz NOT NULL DEFAULT now(), last_error text);
CREATE TABLE billing.api_receipts(
 issuer text NOT NULL, nonce text NOT NULL, expires_at timestamptz NOT NULL,
 PRIMARY KEY(issuer,nonce));
CREATE TABLE billing.product_links(
 binding_id text PRIMARY KEY REFERENCES billing.bindings, environment text NOT NULL,
 peer text NOT NULL, destination text, CHECK(environment IN ('sandbox','production')));
CREATE TABLE billing.purchase_requests(
 account_id text NOT NULL REFERENCES billing.accounts, request_key text NOT NULL,
 request_hash text NOT NULL, invoice_id text NOT NULL REFERENCES billing.invoices,
 PRIMARY KEY(account_id,request_key));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.purchase_requests FOR EACH ROW EXECUTE FUNCTION billing.immutable();
ALTER TABLE billing.invoices ADD COLUMN kind text NOT NULL DEFAULT 'base' CHECK(kind IN ('base','addon'));
DROP INDEX billing.one_collectible_invoice_per_period;
CREATE UNIQUE INDEX one_collectible_invoice_per_period ON billing.invoices(period_id) WHERE status<>'void' AND kind='base';
ALTER TABLE billing.invoices ADD COLUMN effective_at timestamptz;
ALTER TABLE billing.journal_entries DROP CONSTRAINT journal_entries_ledger_account_check;
ALTER TABLE billing.journal_entries ADD CHECK(ledger_account IN ('provider_clearing','service_obligation','unallocated_customer_funds'));
