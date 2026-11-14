CREATE TABLE billing.recurring_mandates (
 id text PRIMARY KEY, account_id text NOT NULL REFERENCES billing.accounts,
 binding_id text NOT NULL REFERENCES billing.bindings,
 sku text NOT NULL, plan_version integer NOT NULL,
 consent_version text NOT NULL, consented_by text NOT NULL, consented_at timestamptz NOT NULL DEFAULT now(),
 request_key text NOT NULL, enrollment_order text NOT NULL UNIQUE,
 provider_subscription_id text UNIQUE,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','active','cancel_requested','canceled')),
 next_payment_at timestamptz, last_failure_at timestamptz,
 FOREIGN KEY(sku,plan_version) REFERENCES billing.plan_versions,
 UNIQUE(account_id,request_key)
);
CREATE UNIQUE INDEX one_live_recurring ON billing.recurring_mandates(binding_id) WHERE state<>'canceled';
CREATE TABLE billing.invoice_collectors (
 invoice_id text PRIMARY KEY REFERENCES billing.invoices,
 method text NOT NULL CHECK(method IN ('manual','recurring')),
 mandate_id text REFERENCES billing.recurring_mandates,
 CHECK((method='recurring')=(mandate_id IS NOT NULL))
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.invoice_collectors FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.invoice_collectors FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
CREATE TABLE billing.recurring_cycles (
 mandate_id text NOT NULL REFERENCES billing.recurring_mandates,
 invoice_id text NOT NULL UNIQUE REFERENCES billing.invoices,
 order_id text NOT NULL UNIQUE REFERENCES billing.provider_orders,
 starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL,
 PRIMARY KEY(mandate_id,starts_at), CHECK(ends_at>starts_at)
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.recurring_cycles FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.recurring_cycles FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
CREATE TABLE billing.recurring_events (
 digest text PRIMARY KEY, mandate_id text NOT NULL REFERENCES billing.recurring_mandates,
 status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.recurring_events FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.recurring_events FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
CREATE FUNCTION billing.mandate_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['state','provider_subscription_id','next_payment_at','last_failure_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','provider_subscription_id','next_payment_at','last_failure_at']) THEN RAISE EXCEPTION 'immutable recurring consent'; END IF;
 IF OLD.provider_subscription_id IS NOT NULL AND NEW.provider_subscription_id IS DISTINCT FROM OLD.provider_subscription_id THEN RAISE EXCEPTION 'immutable provider mandate'; END IF;
 IF NEW.state<>OLD.state AND NOT (OLD.state='pending' AND NEW.state IN ('active','cancel_requested') OR OLD.state='active' AND NEW.state='cancel_requested' OR OLD.state='cancel_requested' AND NEW.state='canceled') THEN RAISE EXCEPTION 'invalid mandate transition'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER mandate_guard BEFORE UPDATE OR DELETE ON billing.recurring_mandates FOR EACH ROW EXECUTE FUNCTION billing.mandate_guard();
