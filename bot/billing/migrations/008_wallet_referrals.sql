ALTER TABLE billing.journal_entries DROP CONSTRAINT journal_entries_ledger_account_check;
ALTER TABLE billing.journal_entries ADD CHECK(ledger_account IN (
 'provider_clearing','service_obligation','unallocated_customer_funds',
 'wallet_cash','wallet_cash_reserved','wallet_promo','wallet_promo_reserved',
 'wallet_referral','wallet_referral_reserved','referral_pending','marketing_expense','test_funding'));
CREATE TABLE billing.wallet_operations (
 id text PRIMARY KEY, account_id text NOT NULL REFERENCES billing.accounts,
 request_key text NOT NULL, request_hash text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('topup','reservation','capture','release','refund','reversal','bonus_reward','referral_reward','reward_available','reward_reversal')),
 bucket text NOT NULL CHECK(bucket IN ('cash','promo','referral')),
 amount_minor bigint NOT NULL CHECK(amount_minor>0),
 parent_id text REFERENCES billing.wallet_operations,
 journal_id text NOT NULL UNIQUE REFERENCES billing.journal_transactions,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(account_id,request_key)
);
CREATE TABLE billing.referral_policies (
 version integer PRIMARY KEY CHECK(version>0),rate_bps integer NOT NULL CHECK(rate_bps IN (2000,2500,3000)),
 hold_days integer NOT NULL CHECK(hold_days BETWEEN 1 AND 90),created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO billing.referral_policies(version,rate_bps,hold_days) VALUES (1,2000,14);
CREATE TABLE billing.referral_codes (
 account_id text PRIMARY KEY REFERENCES billing.accounts,code text NOT NULL UNIQUE,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE billing.referral_bindings (
 referred_account text PRIMARY KEY REFERENCES billing.accounts,referrer_account text NOT NULL REFERENCES billing.accounts,
 policy_version integer NOT NULL REFERENCES billing.referral_policies,created_at timestamptz NOT NULL DEFAULT now(),CHECK(referred_account<>referrer_account)
);
CREATE TABLE billing.referral_rewards (
 id text PRIMARY KEY,referrer_account text NOT NULL REFERENCES billing.accounts,
 referred_account text NOT NULL UNIQUE REFERENCES billing.accounts,
 settlement_id text NOT NULL UNIQUE REFERENCES billing.settlements,
 policy_version integer NOT NULL REFERENCES billing.referral_policies,
 amount_minor bigint NOT NULL CHECK(amount_minor>0),available_after timestamptz NOT NULL,
 wallet_operation_id text NOT NULL UNIQUE REFERENCES billing.wallet_operations,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE billing.referral_reward_events (
 id text PRIMARY KEY,reward_id text NOT NULL REFERENCES billing.referral_rewards,
 kind text NOT NULL CHECK(kind IN ('available','reversed')),amount_minor bigint NOT NULL CHECK(amount_minor>0),
 source_key text NOT NULL UNIQUE,wallet_operation_id text NOT NULL UNIQUE REFERENCES billing.wallet_operations,
 created_at timestamptz NOT NULL DEFAULT now()
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['wallet_operations','referral_policies','referral_codes','referral_bindings','referral_rewards','referral_reward_events'] LOOP
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.%I FOR EACH ROW EXECUTE FUNCTION billing.immutable()',t);
 EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.%I FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable()',t);
 END LOOP;
END $$;
