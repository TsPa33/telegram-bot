-- Explicit local-only migration, never called by application startup or Railway.
-- Existing invoices, fixture ledger, and entitlement outboxes are unchanged.
CREATE TABLE billing.liqpay_sandbox_orders (
    id text PRIMARY KEY CHECK(id ~ '^carpot-wh-sbx-[0-9a-f]{32}$'),
    account_id text NOT NULL REFERENCES billing.accounts,
    invoice_id text NOT NULL UNIQUE,
    amount_minor bigint NOT NULL CHECK(amount_minor>0),
    currency text NOT NULL CHECK(currency='UAH'),
    merchant text NOT NULL CHECK(left(merchant,8)='sandbox_'),
    version integer NOT NULL CHECK(version=7),
    result_url text NOT NULL,
    server_url text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(invoice_id,account_id) REFERENCES billing.invoices(id,account_id),
    UNIQUE(id,merchant)
);
CREATE TABLE billing.liqpay_sandbox_events (
    order_id text NOT NULL REFERENCES billing.liqpay_sandbox_orders,
    digest text NOT NULL CHECK(digest ~ '^[0-9a-f]{64}$'),
    payment_id text,
    provider_status text NOT NULL,
    classification text NOT NULL CHECK(classification IN ('pending','failed','test_success','review')),
    amount_minor bigint NOT NULL CHECK(amount_minor>0),
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(order_id,digest),
    CHECK(classification<>'test_success' OR payment_id IS NOT NULL)
);
CREATE TABLE billing.liqpay_sandbox_payment_ids (
    merchant text NOT NULL,
    payment_id text NOT NULL,
    order_id text NOT NULL,
    PRIMARY KEY(merchant,payment_id),
    FOREIGN KEY(order_id,merchant) REFERENCES billing.liqpay_sandbox_orders(id,merchant)
);
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['liqpay_sandbox_orders','liqpay_sandbox_events','liqpay_sandbox_payment_ids'] LOOP
        EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.%I FOR EACH ROW EXECUTE FUNCTION billing.immutable()',t);
        EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.%I FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable()',t);
    END LOOP;
END $$;
