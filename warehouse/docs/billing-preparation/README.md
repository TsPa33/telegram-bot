# Warehouse billing: disabled preparation, NOT a completed LiqPay integration

## Release boundary

**Checkout, provider callback processing, recurring charges, cancellation and plan changes are disabled.** The official documentation request to `https://www.liqpay.ua/doc/api/internet_acquiring/subscription` failed at the network proxy with `CONNECT 403`. It was not retried. No merchant access or actual sandbox response was obtained. Existing Telegram LiqPay code was read only; its seller subscriptions, callback, secrets and BOT_TOKEN were not imported or changed.

The repository confirms the legacy `pay` payload principle and base64(SHA1(private + data + private)) signing. This does **not** confirm `subscribe`, recurrence event IDs, cancellation, tariff changes, payment-method updates or merchant permissions. Those operations have not been invented.

## Implemented preparation

- Server-defined Standard 1000 UAH / 5 employees / 10 catalogues; Premium 4500 UAH / 10 employees / 50 catalogues. Packs: 300/1, 1200/5, 2000/10. Static version-controlled products are the sole pricing source; no duplicate plans table.
- Additive Alembic revision **e641b3a20f97**, parent **d5298f3b7a10**. Five isolated tables: subscriptions, payment intents, credit grants, catalogue usages, event journal. Workspace FKs, unique request keys, one credit grant per payment, unique donor/modification usage, balance checks. No changes/backfill to stock, prices, receipts, sales, finance or existing accounts. Downgrade intentionally requires review to protect payment evidence.
- Offline fixture ledger: transactional grant/event deduplication, amount/currency/product validation, late failure protection, calendar-month grants, non-expiring packs, monthly-first spending, persisted reservations, atomic successful catalogue+credit commit, free saved-catalogue reopen, failure/partial/empty response rollback. Helpers for confirmed renewal failure/grace (default 3 configurable days); duplicate failure does not extend grace.
- Plan.Parts catalogue path has distinct internal-credit confirmation, separate from provider tokens. Cached recoveries do not trigger new external requests. Failed or uncertain provider acquisition is not represented as successful internal usage. A captured response can finish a pending reservation after a session restart.
- Server checks for expiry/read-only and active employee slots exclude the owner and blocked staff. Original team creation flag and permissions remain authoritative. Owner-only payment history/management; staff do not receive price-plan controls/payment history. Demo bypass is server-side and staging-only.
- Settings UI reads server products, capacities and actual history. It shows inactive billing and the provider blocker; checkout is visibly disabled. No fictional subscriptions, PDF receipts, next-charge dates or live provider results. Identity scope protects cached financial UI when the workspace changes. Day/Night and mobile layout reuse existing tokens.

## Safety configuration

Real staging enforcement is **hard-disabled** until a verified provider adapter and full creation-path coverage exist. A single `WAREHOUSE_BILLING_ENABLED=true` cannot activate it. The only enabled execution mode currently requires all of:

1. `WAREHOUSE_ENV=staging`;
2. `WAREHOUSE_BILLING_ENABLED=true`;
3. `WAREHOUSE_BILLING_FIXTURE_CONTRACT=true`;
4. PostgreSQL host `127.0.0.1` / `localhost` and database name ending `_test`.

These are local test controls, **not Railway setup instructions**. Do not set them on Railway. No Railway Variables were changed. Default deployment leaves existing workspaces operational without subscriptions and accepts no payment callbacks. `WAREHOUSE_BILLING_DEMO_WORKSPACES` is an exact server-side workspace list, effective only in staging; it does not activate billing.

Public `/billing/checkout`, `/billing/cancel-renewal`, `/billing/callback` return 503 without creating payment intent or changing entitlement. The crypto helper and ledger event processor are tested offline; the event processor itself refuses non-local/non-test databases. No real sandbox checkout was performed.

## Validation

Dedicated local PostgreSQL: `warehouse_billing_test`, separate from the existing browser fixture database. No staging DB operations.

- Billing tests: **24 PASS** (`tests/test_billing.py`). Standard/Premium, limits 10/50, packs 1/5/10, duplicate callbacks, invalid amount/currency/status/signature, concurrent reservation, failed/partial/empty catalogue, restart recovery, free reopen, monthly-before-extra, employee slots, expiry/read-only, grace, cross-workspace rejection, owner/staff financial isolation, disabled provider, history while enforcement is off, distinct credit confirmation.
- Existing checklist/category-recovery regression: **13 PASS** in the targeted combined run (34 passed before the final three added billing cases).
- Frontend: **82 PASS** (`billing-unit`, `team-unit`, `parts-tabs-unit`).
- `npm --ignore-scripts run build`: **PASS**, existing Vite chunk-size warning only.
- Browser: **PASS**, real local API and PostgreSQL; Day/Night, 1440/390px, disabled checkout, server products, actual empty history, no overflow/JS errors. Authentication setup creates a synthetic owner; business writes and paid calls during QA: **0**.
- Alembic single head **e641b3a20f97**; full local upgrade completed and updated API startup succeeded. Frontend readiness recognizes this additive head. No manual staging migration was run.

[Day desktop](screenshots/light-1440.png) · [Night desktop](screenshots/dark-1440.png) · [Day mobile](screenshots/light-390.png) · [Night mobile](screenshots/dark-390.png)

## Remaining blockers before billing activation

- Obtain current official LiqPay subscribe/renewal/cancel/tariff-change contract and verified merchant sandbox permissions. Credentials belong only in separately approved server Railway Variables, not chat/Git/UI/logs.
- Implement and test real sandbox intent creation, provider event correlation/public-key validation, exact recurring periods, late/out-of-order renewals, cancellation acknowledgement and safe tariff-change rules. Current mock events are not evidence of LiqPay compatibility.
- Complete quota coverage and acceptance for all legacy/canonical plan creation paths; only the professional Plan.Parts path is wired now. Keep real enforcement disabled until then. Resolve in-flight acquisition without captured response through an explicit reconciliation policy before activation.
- Sandbox end-to-end successful/failed renewal, cancellation and downgrade employee selection remain UNVERIFIED. No production activation is implemented.

Expected auto deployment after push: API (additive migration) and Web, possibly worker according to its existing watch patterns. Railway access is unavailable in this session: deployed SHA, runtime migration and staging QA are **UNVERIFIED**. This is a preparatory release, not PAYMENT READY or RELEASE VERIFIED.
