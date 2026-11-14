-- Explicit Phase 2 upgrade; preserves void invoice/period/line evidence.
ALTER TABLE billing.invoices DROP CONSTRAINT invoices_period_id_key;
ALTER TABLE billing.subscriptions ADD COLUMN calendar_anchor integer CHECK(calendar_anchor BETWEEN 1 AND 31);
UPDATE billing.subscriptions s SET calendar_anchor=EXTRACT(DAY FROM
    (SELECT min(p.starts_at) AT TIME ZONE 'UTC' FROM billing.periods p WHERE p.subscription_id=s.id))::integer
WHERE EXISTS(SELECT 1 FROM billing.periods p WHERE p.subscription_id=s.id);
CREATE UNIQUE INDEX one_collectible_invoice_per_period ON billing.invoices(period_id) WHERE status<>'void';
CREATE TABLE billing.reconciliation_cases (
    id text PRIMARY KEY, account_id text NOT NULL REFERENCES billing.accounts,
    invoice_id text NOT NULL REFERENCES billing.invoices, provider text NOT NULL,
    transaction_id text NOT NULL, event_id text NOT NULL, amount_minor bigint NOT NULL,
    currency text NOT NULL, reason text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(provider,transaction_id)
);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.reconciliation_cases
FOR EACH ROW EXECUTE FUNCTION billing.immutable();
