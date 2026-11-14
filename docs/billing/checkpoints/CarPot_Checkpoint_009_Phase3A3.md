# CarPot Checkpoint 009 — Phase 3A.3

Date: 2026-11-14 (Europe/Kyiv). Branch `feature/carpot-global-liqpay`.
Base package SHA `0ea31b4f9b652bc7f0924e7eb5221cedefaa57cc` (Checkpoint 008); original verified #533 base `b45d3789f4ec7da267da60779cad489866dbb4b6`.
Head: implementation commit containing this checkpoint. PR https://github.com/TsPa33/telegram-bot/pull/534 (Draft).

Completed canonical LiqPay verification/settlement, original shared journal posting, environment-bound full entitlement snapshots, signed delivery and signed post-commit acknowledgement. Inbox, one settlement, immutable financial evidence and outbox are atomic; extra real-confirmed synthetic funds become unallocated liability/reconciliation, never duplicate access. Delivery retries preserve monotonic versions; lost acknowledgement is recoverable. Bounded status polling recovers missed callbacks. Unknown, expired and void orders remain reviewable. Explicit reversal evidence has a separate immutable journal, cumulative amount bounds, idempotency and new rights snapshot; outgoing provider refunds remain unavailable. The candidate reversal envelope needs a separate merchant confirmation flag; ambiguous events remain in review.

The operational database cannot adopt legacy product tables or test money/trials into production. Snapshots select only settlements from the matching operational environment. Original fixture APIs remain local-only; no fixture conversion of verified LiqPay messages.

Warehouse consumes signed proofs into its existing entitlement model. New forward-only migration `b23c45d67e89` (parent a12b34c56d78) records source environment and global binding; no Warehouse ledger or Finance DB access is introduced. Existing policy, quota guard, trial deadline, grace and donor provenance are reused. Explicit owner bind is required; incompatible old identities require migration review. Unknown routes still fail closed; only the new owner-authorized finance routes are added to the registry. Callback receiver has its own service signature, not browser CSRF authority.

Changed files: `bot/billing/{delivery,api,global_core,payments,storage,liqpay_provider}.py`, lifecycle migration 005, finance regression tests; Warehouse `global_billing.py`, existing billing API/model/entitlements/route registry, additive migration, `test_global_billing.py`, and a separately selectable root-context `backend-global.Dockerfile`. The existing staging Dockerfile is unchanged. New image copies only the shared authentication SDK, not the Finance DB service.

Verification: complete financial suite **131 PASS / 0 FAIL** (original 114 retained); synthetic two-DB API→Warehouse pipeline **4 PASS**, including trial→invoice→checkout→verified callback→settlement→signed snapshot→quota projection, cross-environment/tenant tampering, owner/staff isolation and flags OFF. All financial/warehouse data is disposable PostgreSQL. No genuine LiqPay Sandbox request was made. Full independent integrated CI will be run on the completed package series; initial PR CI is separately visible on GitHub.

Staging and production unchanged. No Railway deployment, paid resource, merchant credential, production variable or live worker mutation. Current configuration remains OFF by default. Actual merchant-specific manual/status/reversal/recurring envelopes and provider-issued Sandbox credentials remain external acceptance gates. Sandbox proof cannot activate a production consumer.

Next: Phase 3B, extend the existing WorkspaceBilling cabinet with invoices, history, manual checkout, truthful loading/pending/activation states, responsive themes and lost-response recovery. Then product adapters, separately gated recurring and wallet/referrals.

Resume: read checkpoints 008/009, checkout this branch, install test/API dependencies in a virtualenv; run finance fixture runner and Warehouse `test_global_billing.py` only against explicit loopback *_test DBs. Operational migrations require `python -m bot.billing.api migrate` with a separate explicit migrator DSN; never run against a live database without deployment approval.

Rollback: disable global/checkout/delivery flags, roll back application code, retain all evidence, settlements, journal and outbox, and use reviewed forward migrations. Do not drop environment/binding columns or reverse ledger rows destructively.
