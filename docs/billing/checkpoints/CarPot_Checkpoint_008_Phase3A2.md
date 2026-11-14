# CarPot Checkpoint 008 — Phase 3A.2

Date: 2026-11-14 (Europe/Kyiv). Branch: `feature/carpot-global-liqpay`.
Base: verified PR #533 `b45d3789f4ec7da267da60779cad489866dbb4b6`.
Head: implementation commit containing this checkpoint; resolve with `git log --format=%H -- bot/billing/api.py`.
PR: new global Billing draft, published after this commit; base `feature/carpot-liqpay-phase3a`.

Verified actual heads #527 d10f659, #530 af2eb0a, #528 028d00d, #532 51b87f5, #533 b45d378. PR #533 final finance and full acceptance CI succeeded: runs 43571332942 / 43571332967. Checkpoints through 007 were not present in this checkout; numbering continues as instructed, without fabricating their contents.

Implemented separate explicit operational DB adapter, environment identity, migrator/application separation, no DATABASE_URL fallback or auto migration; retained local-only Database protection. Operational ASGI API exposes canonical catalogue, bindings, cabinet, invoices, checkout/status/refresh, bounded raw callback and admin review. Peer proofs bind method/path/body digest/environment and consume a nonce; membership authorization remains in the Core. Separate explicit v7/SHA3-256 and confirmed v3/SHA-1 profiles have no automatic fallback. Production profile requires explicit merchant confirmation and activation.

Manual checkout uses immutable server invoice terms and one durable canonical intent/order. Candidate provider status client has bounded timeout/retry/backoff/rate limiting, fixed official HTTPS endpoint and no redirects. Shared financial posting was extracted from the original Core; operational verification does not call FixtureAdapter or manufacture fixture events. Verified parallel callbacks post once. Extra confirmed money is retained as unallocated liability/reconciliation, not duplicate access. Unknown and uncollectible states require review. The next package completes durable entitlement delivery/reconciliation operations.

Files: `bot/billing/{storage,global_core,liqpay_provider,payments,api}.py`, `db.py`, `service.py`, `transport.py`, `migrations/004_operational.sql`, `tests/test_operational.py`, `requirements-{api,test}.txt`, `Dockerfile`, `railway.toml`, this checkpoint.

Migration 004 is additive; historical migrations unchanged. New tables extend canonical intents with immutable provider order/evidence/identity, link proof, purchase idempotency and delivery metadata. Add-ons share the paid base period but have separate invoices and explicit effective timestamps. Existing account/invoice/journal/outbox remain the financial authority.

Tests: original 114 financial tests PASS after shared posting extraction; 12 new operational/provider/API cases PASS on fresh disposable PostgreSQL. No real provider request or credential test was performed. Independent CI for this new branch pending publication.

Staging: Warehouse/OEM/progress deployment reported by the owner is unchanged; this package is not deployed. Production: unchanged. No Railway resources/variables were created or changed. Railway Docker/TOML is preparation only. Runtime and migration DSNs must be separate scoped credentials; no secret values are committed.

Blockers: actual merchant protocol/credentials and real Sandbox acceptance; approval of separate Billing database/service/deployment; production operational role setup. All default network/payment/rollout flags remain OFF. Next: Phase 3A.3, signed environment-bound entitlement outbox delivery, recovery, refund/reversal evidence and operational trial/cancellation.

Resume: checkout this branch; read this checkpoint and migration 004; run `python -m bot.billing.run_fixture_tests` with test requirements and managed Docker. Never substitute live DSNs in the fixture runner. Operational migrations require explicit `BILLING_MIGRATOR_DSN` and environment, and separate deployment approval.

Rollback: disable routing/checkout flags and revert application artifacts; retain invoices, evidence, journal, settlements and outbox. Corrective migrations only forward. No destructive rollback.
