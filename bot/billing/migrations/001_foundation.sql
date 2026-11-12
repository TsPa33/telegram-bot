-- Local-only additive migration. Never loaded by legacy or Warehouse migration runners.
CREATE TABLE billing.accounts (
    id text PRIMARY KEY, owner_principal text NOT NULL, kind text NOT NULL
        CHECK (kind IN ('company','personal')), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE billing.memberships (
    account_id text NOT NULL REFERENCES billing.accounts, principal_id text NOT NULL,
    permissions text[] NOT NULL, PRIMARY KEY(account_id,principal_id)
);
CREATE TABLE billing.bindings (
    id text PRIMARY KEY, account_id text NOT NULL REFERENCES billing.accounts,
    workspace_id text NOT NULL, product text NOT NULL, evidence_id text NOT NULL UNIQUE,
    verified_by text NOT NULL, verified_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(product,workspace_id), UNIQUE(id,account_id)
);
CREATE TABLE billing.plan_versions (
    sku text NOT NULL, version integer NOT NULL CHECK(version>0), product text NOT NULL,
    kind text NOT NULL CHECK(kind IN ('base','addon')), amount_minor bigint NOT NULL CHECK(amount_minor>0),
    currency text NOT NULL CHECK(currency='UAH'), vehicle_capacity integer NOT NULL CHECK(vehicle_capacity>=0),
    employees integer NOT NULL CHECK(employees>=0), PRIMARY KEY(sku,version)
);
CREATE TABLE billing.subscriptions (
    id text PRIMARY KEY, account_id text NOT NULL, binding_id text NOT NULL,
    sku text NOT NULL, plan_version integer NOT NULL, status text NOT NULL DEFAULT 'inactive'
        CHECK(status IN ('inactive','active','canceled')), projection_version bigint NOT NULL DEFAULT 0,
    FOREIGN KEY(binding_id,account_id) REFERENCES billing.bindings(id,account_id),
    FOREIGN KEY(sku,plan_version) REFERENCES billing.plan_versions,
    UNIQUE(binding_id), UNIQUE(id,account_id)
);
CREATE TABLE billing.periods (
    id text PRIMARY KEY, account_id text NOT NULL, subscription_id text NOT NULL,
    starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL CHECK(ends_at>starts_at),
    FOREIGN KEY(subscription_id,account_id) REFERENCES billing.subscriptions(id,account_id),
    UNIQUE(subscription_id,starts_at), UNIQUE(id,account_id)
);
CREATE TABLE billing.invoices (
    id text PRIMARY KEY, account_id text NOT NULL, period_id text NOT NULL UNIQUE,
    request_key text NOT NULL, request_hash text NOT NULL, amount_minor bigint NOT NULL CHECK(amount_minor>0),
    currency text NOT NULL CHECK(currency='UAH'), status text NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','open','paid','void')),
    FOREIGN KEY(period_id,account_id) REFERENCES billing.periods(id,account_id),
    UNIQUE(account_id,request_key), UNIQUE(id,account_id)
);
CREATE TABLE billing.invoice_lines (
    id text PRIMARY KEY, account_id text NOT NULL, invoice_id text NOT NULL,
    sku text NOT NULL, plan_version integer NOT NULL, quantity integer NOT NULL CHECK(quantity>0),
    unit_amount_minor bigint NOT NULL CHECK(unit_amount_minor>0),
    amount_minor bigint NOT NULL CHECK(amount_minor>0),
    FOREIGN KEY(invoice_id,account_id) REFERENCES billing.invoices(id,account_id),
    FOREIGN KEY(sku,plan_version) REFERENCES billing.plan_versions
);
CREATE TABLE billing.intents (
    id text PRIMARY KEY, account_id text NOT NULL, invoice_id text NOT NULL UNIQUE,
    provider text NOT NULL CHECK(provider='fixture'), environment text NOT NULL CHECK(environment='test'),
    merchant text NOT NULL CHECK(merchant='disposable-fixture'),
    FOREIGN KEY(invoice_id,account_id) REFERENCES billing.invoices(id,account_id), UNIQUE(id,account_id)
);
CREATE TABLE billing.attempts (
    id text PRIMARY KEY, account_id text NOT NULL, intent_id text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','failed','confirmed')),
    FOREIGN KEY(intent_id,account_id) REFERENCES billing.intents(id,account_id), UNIQUE(intent_id)
);
CREATE TABLE billing.webhook_inbox (
    provider text NOT NULL, event_id text NOT NULL, payload_hash text NOT NULL,
    account_id text NOT NULL REFERENCES billing.accounts, intent_id text NOT NULL,
    status text NOT NULL CHECK(status IN ('pending','success','failure')),
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(provider,event_id),
    FOREIGN KEY(intent_id,account_id) REFERENCES billing.intents(id,account_id)
);
CREATE TABLE billing.journal_transactions (
    id text PRIMARY KEY, account_id text NOT NULL REFERENCES billing.accounts,
    external_key text NOT NULL UNIQUE, currency text NOT NULL CHECK(currency='UAH'),
    created_at timestamptz NOT NULL DEFAULT now(), created_xid bigint NOT NULL DEFAULT txid_current(),
    UNIQUE(id,account_id)
);
CREATE TABLE billing.journal_entries (
    id text PRIMARY KEY, transaction_id text NOT NULL, account_id text NOT NULL,
    ledger_account text NOT NULL CHECK(ledger_account IN ('provider_clearing','service_obligation')),
    amount_minor bigint NOT NULL CHECK(amount_minor<>0),
    FOREIGN KEY(transaction_id,account_id) REFERENCES billing.journal_transactions(id,account_id)
);
CREATE TABLE billing.settlements (
    id text PRIMARY KEY, account_id text NOT NULL, invoice_id text NOT NULL UNIQUE,
    intent_id text NOT NULL UNIQUE, provider text NOT NULL, transaction_id text NOT NULL,
    journal_id text NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(provider,transaction_id),
    FOREIGN KEY(invoice_id,account_id) REFERENCES billing.invoices(id,account_id),
    FOREIGN KEY(intent_id,account_id) REFERENCES billing.intents(id,account_id),
    FOREIGN KEY(journal_id,account_id) REFERENCES billing.journal_transactions(id,account_id)
);
CREATE TABLE billing.outbox (
    id text PRIMARY KEY, account_id text NOT NULL REFERENCES billing.accounts,
    aggregate_id text NOT NULL, version bigint NOT NULL CHECK(version>0),
    topic text NOT NULL CHECK(topic='billing.entitlement.snapshot.v1'), payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), delivered_at timestamptz,
    UNIQUE(aggregate_id,version)
);

CREATE FUNCTION billing.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable financial evidence'; END $$;
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['bindings','plan_versions','periods','invoice_lines','intents',
        'webhook_inbox','journal_transactions','journal_entries','settlements'] LOOP
        EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.%I FOR EACH ROW EXECUTE FUNCTION billing.immutable()',t);
        EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.%I FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable()',t);
    END LOOP;
END $$;

-- A journal transaction cannot commit empty, unbalanced or single-sided.
CREATE FUNCTION billing.check_journal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target text; total numeric; n integer;
BEGIN
    IF TG_TABLE_NAME='journal_transactions' THEN target:=NEW.id; ELSE target:=NEW.transaction_id; END IF;
    SELECT coalesce(sum(amount_minor),0),count(*) INTO total,n
      FROM billing.journal_entries WHERE transaction_id=target;
    IF total<>0 OR n<2 THEN RAISE EXCEPTION 'unbalanced journal'; END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER balanced_header AFTER INSERT ON billing.journal_transactions
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION billing.check_journal();
CREATE CONSTRAINT TRIGGER balanced_entry AFTER INSERT ON billing.journal_entries
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION billing.check_journal();
CREATE FUNCTION billing.entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM billing.journal_transactions
        WHERE id=NEW.transaction_id AND created_xid=txid_current()) THEN
        RAISE EXCEPTION 'cannot append to posted journal';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER entry_guard BEFORE INSERT ON billing.journal_entries
    FOR EACH ROW EXECUTE FUNCTION billing.entry_guard();

CREATE FUNCTION billing.invoice_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE total numeric;
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'invoice deletion forbidden'; END IF;
    IF (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN
        RAISE EXCEPTION 'immutable invoice terms';
    END IF;
    IF NEW.status=OLD.status THEN RETURN NEW; END IF;
    IF NOT ((OLD.status='draft' AND NEW.status IN ('open','void')) OR
            (OLD.status='open' AND NEW.status IN ('paid','void'))) THEN
        RAISE EXCEPTION 'invalid invoice transition';
    END IF;
    IF NEW.status IN ('open','paid') THEN
        SELECT coalesce(sum(amount_minor),0) INTO total FROM billing.invoice_lines WHERE invoice_id=NEW.id;
        IF total<>NEW.amount_minor THEN RAISE EXCEPTION 'invoice lines mismatch'; END IF;
    END IF;
    IF NEW.status='paid' AND NOT EXISTS(SELECT 1 FROM billing.settlements WHERE invoice_id=NEW.id) THEN
        RAISE EXCEPTION 'payment requires settlement';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER invoice_guard BEFORE UPDATE OR DELETE ON billing.invoices
    FOR EACH ROW EXECUTE FUNCTION billing.invoice_guard();
CREATE FUNCTION billing.line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE state text;
BEGIN
    SELECT status INTO state FROM billing.invoices WHERE id=NEW.invoice_id FOR UPDATE;
    IF state<>'draft' THEN RAISE EXCEPTION 'issued invoice lines immutable'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER line_guard BEFORE INSERT ON billing.invoice_lines
    FOR EACH ROW EXECUTE FUNCTION billing.line_guard();

CREATE FUNCTION billing.outbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'outbox evidence cannot be deleted'; END IF;
    IF (to_jsonb(NEW)-'delivered_at') IS DISTINCT FROM (to_jsonb(OLD)-'delivered_at')
        OR (OLD.delivered_at IS NOT NULL AND NEW.delivered_at IS DISTINCT FROM OLD.delivered_at) THEN
        RAISE EXCEPTION 'immutable outbox envelope';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER outbox_guard BEFORE UPDATE OR DELETE ON billing.outbox
    FOR EACH ROW EXECUTE FUNCTION billing.outbox_guard();
