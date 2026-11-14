# CarPot Checkpoint 011 — Phase 3C

2026-11-14 Europe/Kyiv. Branch `feature/carpot-global-liqpay`; original base #533 `b45d3789f4ec7da267da60779cad489866dbb4b6`; package base `21ff96e`. Head: containing commit, resolve `git log -1 --format=%H -- docs/billing/checkpoints/CarPot_Checkpoint_011_Phase3C.md`. Draft PR https://github.com/TsPa33/telegram-bot/pull/534.

Implemented opt-in Telegram/garage/CRM/site adapters over the same canonical Billing Core. Legacy UUID checkout and callbacks retain their previous route; new `carpot-{environment}-…` orders go to the canonical verifier and cannot fall through to legacy activation. Legacy signature comparison is constant-time. Peer requests bind HTTP method/path/body, environment, nonce and principal; product allowlists restrict binding authority. Financial membership determines returned permissions.

Product catalogue migration 006 records immutable approved existing terms: garage 99/199/299 UAH for 1/5/10 slots and 30 days; CRM 99 UAH/30 days; Standard site 499 UAH/year. Warehouse retains its existing calendar-month catalogue. Plus (1499 UAH) and custom (from 4999 UAH) remain quote/fulfillment-gated: the existing code does not define an unambiguous renewal/fulfillment contract. No guessed subscription term or price change. A non-default deployed CRM price also requires a new approved catalogue version before its flag is enabled.

Telegram URL buttons open short-lived HMAC capability links on the Billing service. The server renders only a POST to the fixed official LiqPay URL; no payment secrets or card inputs. Capability grants no financial-history access. Product SDK uses bounded authenticated HTTPS; no Finance DSN in the bot.

Additive bot SQL `20261114_global_billing_projection.sql` stores bindings, orders and monotonic rights projections only. Canonical garage limits are continuous; original active legacy slots remain available. CRM read projections preserve existing/free access. Standard site fulfillment creates a missing site without overwriting any legacy site configuration; only sites with explicit new fulfillment provenance expire with their canonical period. Sandbox cannot run with a production consumer configuration. All product flags default OFF. Existing payments/subscription history is never rewritten.

Read-only legacy export preview detects duplicates and existing mappings. A mapping cannot mint a settlement from a legacy status: it requires already-verified canonical provider evidence, matching invoice/settlement and immutable uniqueness. Historical orders without independently correlated evidence require review and keep their legacy access/history.

Files: `bot/billing/{api,global_core,products,client,public_checkout,liqpay_provider}.py`, migration 006, product/operational tests and test dependencies; explicit adapters in existing `bot/services/liqpay_service.py`, `bot/api/liqpay_callback.py`, seller/CRM/site repositories; new `bot/services/global_billing.py` and additive bot projection migration. Foundation boundary test now enforces the exact authorized adapter surface, original legacy checkout AST, and flags-OFF behavior instead of forbidding the integration explicitly requested in this phase; no tests skipped, deleted or waived.

Verification: product SDK/hosted capability/immutable terms/preview tests PASS; real two-database Telegram→Core→signed projection→garage PASS, including repeated sync and legacy flags OFF. Subsequent integrated finance suite (including recurring/wallet work in the working tree) 139 PASS/0 FAIL; final independent head CI at Checkpoint 014. Genuine merchant Sandbox not exercised.
CI: https://github.com/TsPa33/telegram-bot/pull/534/checks.
Staging/production unchanged. No deployment or live DB/secret/variable mutation.
Blockers: merchant-issued Sandbox profile/keys, approved deployment, Plus/custom fulfillment terms, explicit reviewed cross-service company linking/export mapping. No inference from email/username.
Next: separately gated recurring lifecycle (Phase 4), then test-only wallet/referrals.
Resume: checkpoints 008–011; only disposable *_test databases for tests. Apply financial and bot projection migrations explicitly as separate deployment steps after approval.
Rollback: flags OFF and code rollback; retain all legacy and canonical history/projections; corrective migrations forward only.
