-- Explicit operator-only psql script, after migrations, on the DEDICATED Billing DB.
-- Usage: psql "$BILLING_MIGRATOR_DSN" -v ON_ERROR_STOP=1 -v app_role=billing_app -f bot/billing/deploy/grants.sql
-- Create a separate NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT application login out of band.
-- Never grant the application membership in the migrator/owner role.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA billing FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA billing FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA billing FROM PUBLIC;
GRANT USAGE ON SCHEMA billing TO :"app_role";
GRANT SELECT ON ALL TABLES IN SCHEMA billing TO :"app_role";
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA billing TO :"app_role";
GRANT INSERT ON billing.accounts,billing.memberships,billing.bindings,billing.subscriptions,
 billing.periods,billing.invoices,billing.invoice_lines,billing.intents,billing.attempts,
 billing.webhook_inbox,billing.journal_transactions,billing.journal_entries,billing.settlements,
 billing.outbox,billing.reconciliation_cases,billing.warehouse_trials,
 billing.provider_orders,billing.provider_evidence,billing.provider_transactions,
 billing.outbox_delivery,billing.api_receipts,billing.product_links,billing.purchase_requests,
 billing.provider_polling,billing.reversals,billing.legacy_mappings,
 billing.recurring_mandates,billing.invoice_collectors,billing.recurring_cycles,billing.recurring_events,
 billing.wallet_operations,billing.referral_codes,billing.referral_bindings,
 billing.referral_rewards,billing.referral_reward_events TO :"app_role";
-- SELECT FOR UPDATE needs UPDATE privilege on at least one column. Immutable triggers
-- protect bindings; account IDs remain constrained by canonical foreign keys.
GRANT UPDATE(id) ON billing.accounts,billing.bindings TO :"app_role";
GRANT UPDATE(status) ON billing.invoices,billing.attempts TO :"app_role";
GRANT UPDATE(sku,plan_version,status,projection_version,calendar_anchor) ON billing.subscriptions TO :"app_role";
GRANT UPDATE(delivered_at) ON billing.outbox TO :"app_role";
GRANT UPDATE(attempts,next_attempt_at,last_error) ON billing.outbox_delivery,billing.provider_polling TO :"app_role";
GRANT UPDATE(plan) ON billing.warehouse_trials TO :"app_role";
GRANT UPDATE(state,provider_subscription_id,next_payment_at,last_failure_at) ON billing.recurring_mandates TO :"app_role";
-- No DELETE/TRUNCATE/DDL, catalogue mutation, schema version mutation or identity mutation.
GRANT UPDATE(principal_id) ON billing.memberships TO :"app_role";
GRANT UPDATE(id) ON billing.settlements,billing.referral_rewards TO :"app_role";
