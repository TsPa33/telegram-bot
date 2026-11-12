# Controlled rollout plan — not executed

1. Review Draft PR, exact SHA and independent full CI; resolve release-blocking baseline
   test issues. Approve product rules and identify initial pilot companies.
2. Approve finance placement and verified organizational identity; establish production
   service authentication/key rotation and authenticated delivery. Current adapter is
   intentionally limited to loopback *_test databases, not deployable by toggling a flag.
3. Backup and test restore; inspect deployed migration ancestry. Apply additive schemas
   only under a separately approved staging change. Never alter import-worker here.
4. Keep flags OFF and all existing companies in compatibility. Inventory existing
   subscriptions/credits without automatic conversion, debt or trial grants.
5. Produce read-only dry-run donor/team/stock/provenance reports per approved workspace.
   Review archived physical stock, missing historical origin, negative anomalies and
   would-block operations. A deleted historical donor link cannot be magically recovered;
   reconcile against immutable audit evidence with owner review.
6. Bind authenticated owner/company, compare signed full rights snapshots and usage,
   then approve one workspace enrollment. Start in dry_run, then explicit enforce.
7. Verify last-place concurrency, reserves, old-order completion, returns, staff access,
   trial deadline and expiry in staging using synthetic data only.
8. Expand pilots only after evidence review. Roll back to compatibility / disable flags;
   preserve projections, immutable receipts, returns, inventory and finance records.

## Phase 3 LiqPay readiness

Not production-ready. Legacy callback/routing and secrets are unchanged. Mandatory gates:
merchant-specific API/signature contract (v3/SHA-1 vs v7/SHA3-256), hosted Checkout
capabilities, verified provider events, amount/currency/merchant correlation, raw durable
inbox/reconciliation, operational finance DB, trusted org binding and real delivery.
The void reissue and excess-payment cases now have explicit local finance regression
coverage, but this does not establish refund/recurring/payout capability. Only then add
manual Checkout/status/reconciliation and separately authorized sandbox acceptance.
Recurring, wallet, referrals, payouts and live enforcement remain separate approvals.
