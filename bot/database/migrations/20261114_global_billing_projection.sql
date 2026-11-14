-- Product projections only; no copied settlements, balances, payment status or provider secrets.
CREATE TABLE IF NOT EXISTS global_billing_bindings (
 seller_id bigint NOT NULL REFERENCES sellers(id), product text NOT NULL,
 environment text NOT NULL CHECK(environment IN ('sandbox','production')),
 principal_id text NOT NULL, account_id text NOT NULL, binding_id text NOT NULL UNIQUE,
 PRIMARY KEY(seller_id,product,environment)
);
CREATE TABLE IF NOT EXISTS global_billing_orders (
 order_id text PRIMARY KEY, binding_id text NOT NULL REFERENCES global_billing_bindings(binding_id)
);
CREATE TABLE IF NOT EXISTS global_billing_projections (
 binding_id text PRIMARY KEY REFERENCES global_billing_bindings(binding_id),
 version bigint NOT NULL CHECK(version>0), event_id text NOT NULL, digest text NOT NULL,
 payload jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS global_billing_fulfillment (
 binding_id text PRIMARY KEY REFERENCES global_billing_bindings(binding_id),
 site_id bigint NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
);
