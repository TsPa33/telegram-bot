# Control Center checkpoint 007 — security stabilization and full regression gate

Date: 2026-11-16 Europe/Kyiv. Branch `feature/carpot-control-center-warehouse`.
Original integration base: `fdaef3c638765ca845692727f90c9f140395891b`.
Original review head: `2bfb5f931f5b6f2004ead35467137c63df7a8566`.
Integrated onto newer branch head `2a610afa` (preserving all intervening source, preview, credential-rotation and UX commits).
Head: containing code commit; resolve `git log -1 --format=%H -- docs/control-center/Checkpoint_007_Stabilization.md`.
Draft PR created and verified: https://github.com/TsPa33/telegram-bot/pull/539.
GitHub API is usable in this session; no network-policy change/new token needed.

## Clean baseline

An untouched checkout of package base completed the entire Warehouse `tests unit_tests`
suite against dedicated disposable PostgreSQL: **1025 PASS, 1 existing opt-in skip,
0 FAIL / 0 ERROR**, 1349.84 seconds. Log `/workspace/cc-frozen-full.log`, XML
`/workspace/cc-frozen-full.xml`. This closes the original six mixed-edit setup errors
for that frozen baseline; it is not mislabeled as a later-head test. The skip remains
the original opt-in 100k smart-search benchmark; no skip/xfail/assertion was weakened.

## Findings and changes

Concurrent assignment could leave grants for two managers. Assignment now locks the
company before replacing its grant. Scoped company reads/mutations hold a compatible
row lock and recheck the grant in a fresh statement after waiting, preventing the
READ COMMITTED pre-lock snapshot from authorizing a revoked manager's note. Tests
interleave actual HTTP requests at a PostgreSQL grant-delete boundary and observe
real contention, verifying both reassignment and revoked-note denial.

Staff privilege changes now require a fresh, single-use MFA code in addition to the
MFA session/CSRF/Origin checks. Attempts have separate persistent account/IP budgets;
code consumption, role change, session revoke and audit commit together. Mutations
serialize on the actor's staff row. No new schema or financial mutation is introduced.

Existing domain-separated cookie-bound CSRF recovery via `/auth/csrf` is preserved,
including compatibility with pre-upgrade sessions and new tabs. No extra readable
CSRF/auth cookie was added. Browser expected-staff assertions reject an actor switch;
revoked sessions clear protected UI. Existing new-tab/stale-proof logout browser
checks remain, plus a revoked-session UI check on both engines.

Credential rotation now has a separate persistent attempt budget and safe denied
audit. Failed rotation cannot unlock automatic source refresh: the prerequisite
explicitly requires a successful rotation. No worker was started or deployed by
this task. Previously added preview/source/UX functionality is preserved.

## Validation and final gate

- Locked CC dependency environment: **44 PASS / 0 FAIL / 0 SKIP** on the integrated source (including inherited tests and new stabilization regressions).
- Frontend: **639 PASS**, build PASS (existing customer bundle advisory only).
- Local Chromium/WebKit matrix: **32 PASS**, four themes × four widths, including
  the new session cases; actual guarded local API/PostgreSQL, synthetic staff only.
- Workflow `control-center.yml` now runs **all Warehouse tests and unit_tests**,
  replacing its selected 119-case job, with full Git history and a 50-minute bound.
  Other staff/browser/Billing gates remain. This is a required final frozen-head gate;
  at checkpoint creation that new independent run is pending. Final PR report records
  exact completed run IDs/results; do not count pending CI as passed.

Files: CC security/API, rotation prerequisite in the existing CC sync worker, corresponding security/projection/rotation regressions, isolated staff frontend
API/session lifecycle, browser tests, CC workflow, README and this checkpoint.
Migrations: none. Warehouse head remains c34d56e78f90; CC schema remains 001.
Changes outside Warehouse: none in this stabilization package. No legacy/customer
stock/orders, Catalogue/OEM or Billing financial implementation was changed by this package.

Staging/production: unchanged, not deployed/accepted. No real credentials, staff
accounts, paid resources, source data, financial operations, customer messages,
Railway flags/variables or unrelated services were changed. Creation flags stay OFF.

Deferred scope remains other product adapters, tombstone automation, metric policies,
financial mutation/impersonation/export, MFA recovery UI and key-rotation automation.
Next: verify exact-head independent full gate, then review-only handoff. Any staging
rollout requires separate owner authorization and verified runtime inventory.

Resume: verify PR539 current head, read this checkpoint and README, inspect exact-head
CI. Test only explicit loopback disposable *_test DBs. Do not edit a checkout while
its full suite is running; immutable source snapshots/CI checkouts preserve provenance.
Rollback: flags OFF and prior code; keep audit/notes/grants/source references and all
customer/financial history. No destructive downgrade or schema deletion.
