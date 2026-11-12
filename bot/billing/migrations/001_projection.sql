CREATE SCHEMA billing_projection;
CREATE TABLE billing_projection.bindings (
    workspace_id text NOT NULL, product text NOT NULL, account_id text NOT NULL,
    subscription_id text NOT NULL, PRIMARY KEY(workspace_id,product), UNIQUE(subscription_id)
);
CREATE TABLE billing_projection.inbox (
    event_id text PRIMARY KEY, payload_hash text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE billing_projection.snapshots (
    subscription_id text PRIMARY KEY REFERENCES billing_projection.bindings(subscription_id),
    version bigint NOT NULL CHECK(version>0), payload jsonb NOT NULL,
    CHECK(payload->>'environment'='test'),
    CHECK(payload->>'activates_real_services'='false')
);
