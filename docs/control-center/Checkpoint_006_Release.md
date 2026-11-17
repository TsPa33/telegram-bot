# Control Center checkpoint 006 — validation and review handoff

Date: 2026-11-15 Europe/Kyiv.
Branch: feature/carpot-control-center-warehouse (pushed).
Base: fdaef3c638765ca845692727f90c9f140395891b.
Implementation: 4e4a5f07e6f977d967b4b9d9277d929c61055adb.
Final executable/CI configuration: 55c10e16b4fc160157317410fb055376c0177a1e.
Subsequent commits only document completed packages/PR handoff; do not claim a
new run on a docs-only commit. Resolve this checkpoint's commit with git log.
PR: NOT created. Native Git push works; gh pr create --draft fails at
https://api.github.com/graphql with Forbidden. No PR number fabricated.

## Current baseline and independent evidence

Initial refs/ancestry in checkpoint 001 remain valid. Additional read-only
public GitHub pages establish PR538 is Draft, titled onboarding v2, at fdaef3c.
Its checks page shows ten successful jobs across runs 43646688686, 43646688773,
43646688828. In particular base full Warehouse run reports 32m51s. These are
PR538 evidence, not substituted PR534 results and not Railway runtime evidence.

New exact-code independent gates:
- https://github.com/TsPa33/telegram-bot/actions/runs/43681872714
  implementation 4e4a5f07: staff-and-projections and browsers successful.
- Run 43682327899 on workflow 8bf83c45: staff, browsers and Warehouse successful;
  finance failed. Diagnosed runner prerequisite: actions/checkout depth 1 lacks
  historical 160ffbe... required by unchanged test_legacy_and_warehouse_unchanged.
- https://github.com/TsPa33/telegram-bot/actions/runs/43682622139
  55c10e16b4fc160157317410fb055376c0177a1e: ALL FOUR JOBS SUCCESSFUL.
  staff-and-projections job 132716312582; browsers 132716312471;
  billing-compatibility 132716312644; warehouse-regressions 132716312584.
  Runner correction fetch-depth:0, no assertion/skip weakening.

Conclusions verified through public run/job HTML with matching commit titles;
API and authenticated job logs/artifact XML remain inaccessible. Suite sizes
below are actual local results/collection and committed runner contracts, not
invented downloaded CI XML. Browser job has both engines/no override (32 cases).

## Local validation

All databases were explicit loopback disposable *_test databases. No live test.
- CC: 29 PASS / 0 FAIL / 0 SKIP using requirements-control-center.lock with
  --require-hashes, a dedicated locked venv and actual restricted cc_app/cc_source.
  Command: pytest -c warehouse/backend/control_center_tests/pytest.ini
  warehouse/backend/control_center_tests -q (root cwd, required test URLs set).
- Billing: 145 PASS / 0 FAIL / 0 SKIP using bot/billing/pytest.ini and two separate
  finance/projection DBs. Includes actual signed staff read tests and no mutation.
- Frontend: node --test tests/*unit*.mjs -> 639 PASS / 0 FAIL / 0 SKIP.
- npm run build -> PASS including existing 275 prebuild checks; separate control
  and customer entries emitted. Existing >500KB Warehouse chunk advisory only.
- New local browser: 16 Chromium PASS / 0 FAIL, four widths x four themes,
  genuine local staff API/DB, explicit synthetic fixtures, no external provider.
  Includes masking/notes/queue/unavailable finance, focus, keyboard, reduced motion,
  no page overflow and deliberate loading/error/empty/stale UI fault injection.
- Local WebKit launch UNRUN: browser absent, cdn.playwright.dev denied; official
  container download also Forbidden. Independent browser job succeeded instead.
- Existing corporate-ux-v2-browser.mjs PASS: real customer auth, stock, sidebar,
  inline picker, themes, responsive layouts, sales lifecycle and buyer history,
  new Control Center flag OFF. Existing script unchanged.
- Non-root backend-control image built; imports staff mount as UID10001; fixtures
  excluded. Europe/Kyiv summer UTC+03 timezone assertion PASS in final image.
- Full original Warehouse tests+unit_tests: 1019 PASS, 1 existing SKIP, 6 setup
  ERRORS, 1875.02 seconds. Skip is test_smart_search_perf::test_scale, original
  WAREHOUSE_SMART_PERF opt-in 100k benchmark. No skip added by this change.
  The six errors were Global Billing fixtures: suite started while the caller
  registration changed from three to four args and loaded mixed old/new modules.
  This execution is NOT a clean full pass. Fresh test_global_billing.py on new
  DBs: 7 PASS / 0 FAIL. Frozen-source CI Warehouse job: successful across the
  selected 119 collected cases, no skip markers in those files. No unresolved
  application failure inferred from the mixed-snapshot run; raw outcome retained.
- git diff --check PASS. Protected customer/legacy/Catalogue/OEM/service/model/
  Warehouse migration source comparison against base unchanged. Application tree
  identical between implementation 4e4a5f07 and final CI commit 55c10e16.

Initial installation/collection issues were resolved without changing protected
files: writable npm/uv caches, explicit pytest root/config/pythonpath, required
asyncpg/dotenv test dependencies. TLS/hashes never disabled. No bypassed artifact
is used. CI has its own fresh environments and real PostgreSQL services.

## Files and operational readiness

New app/control_center modules, separate additive SQL/grants, optional hashed
requirements, prepared non-root Dockerfile, separate React entry/components,
CI gate and targeted tests; numbered checkpoints 001–006 plus README/PR description.
Minimal outside-Warehouse diff: Billing staff reader, two API registration lines,
reader tests and shared new CI definition. No other CarPot product implementation
changed. Warehouse source migration head remains c34d56e78f90; CC schema 001.

Local: implemented and tested. Staging: prepared instructions/image only, NOT
rolled out; service/deployment/flags unknown. Production: NOT deployed/accepted.
No paid resources, merchant calls, refunds, messages, OEM import, live migration,
new live staff or unrelated restart. Feature flags remain OFF by default.

Deferred by scope: other product adapters/legacy Support integration, financial
mutations/impersonation/PII export, approved aggregate metric policies, automatic
source tombstone propagation, MFA recovery UI/key-rotation automation. No fake
menu/data is presented for deferred products. Source-deleted rows retain history
and stale indicators; directory is not claimed a complete live census.

## Blocker, next step and resume

Only outstanding external delivery blocker: GitHub API access for Draft PR.
Runtime network status remains revision 1, restricted policy, no custom domains.
A draft addition of api.github.com and cdn.playwright.dev was saved for review;
not applied/published. Existing package-manager presets preserved. No secret,
application variable, Railway configuration or deployment changed.

To finish PR creation: apply the approved GitHub API access through environment
settings (saved source draft requires review/save and environment publication,
not a Railway deployment), then retry with the existing injected authentication.
Do not request a new token merely because API egress was denied.

Resume in existing checkout (no new worktree):
1. Verify branch/status, remote head and that base feature/carpot-referral-onboarding
   still matches the verified integration lineage. Keep changes scoped.
2. Read README and checkpoints; compare current application tree to 55c10e16.
3. Create the already-authorized Draft PR, stacked on feature/carpot-referral-onboarding:
   gh pr create --draft --base feature/carpot-referral-onboarding
   --head feature/carpot-control-center-warehouse
   --title 'CarPot Control Center: isolated Warehouse-first hybrid staff CRM'
   --body-file docs/control-center/PR_DESCRIPTION.md
   (one command with normal shell line continuations).
4. Record actual PR URL and exact completed PR-head checks; do not merge/deploy.

Future rollout requires separate authorization and verified runtime inventory.
Rollback: feature flags OFF, previous code, keep staff audit/notes/source links
and every customer/financial history. No destructive downgrade.
