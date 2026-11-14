CREATE TABLE billing.provider_polling(intent_id text PRIMARY KEY REFERENCES billing.intents, attempts integer NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now(), last_error text);
CREATE TABLE billing.reversals(
 id text PRIMARY KEY, settlement_id text NOT NULL REFERENCES billing.settlements,
 provider text NOT NULL, provider_event_id text NOT NULL, amount_minor bigint NOT NULL CHECK(amount_minor>0),
 reason text NOT NULL CHECK(reason IN ('refund','reversal','chargeback')),
 journal_id text NOT NULL UNIQUE REFERENCES billing.journal_transactions,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(provider,provider_event_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.reversals FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.reversals FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
