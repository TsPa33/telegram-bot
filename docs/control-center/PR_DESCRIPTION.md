# CarPot Control Center: isolated Warehouse-first hybrid staff CRM

Warehouse staff need a global company view without borrowing customer DIRECTOR
sessions or exposing unrestricted financial access. Adds a separate /control/
React entry and /api/control staff realm with MFA, durable throttling, hashed
revocable sessions, company-scoped roles and atomic append-only audit.

The hybrid BFF uses a small independently permissioned PostgreSQL schema and
explicit bounded read-only Warehouse sweeps. It shows workspace owners/employees,
entitlement limits/usage, verified/unlinked/conflicting Billing context, internal
notes, manager assignments and a work queue. Lists/overview do not fan out to
Billing. Amounts require an explicit permission; Support never receives them.
The only dependency outside Warehouse is a gated, independently signed Warehouse
finance reader in Billing. It writes nonce receipts, not financial records.

Both feature flags default OFF. Independent additive Control Center schema 001;
Warehouse Alembic stays c34d56e78f90. Operator-only provisioning/migrations/grants,
readiness, rollout and non-destructive rollback are in README/checkpoints.
No live deployment, migration, staff account, credential, price or paid resource
was changed. Telegram, Seller CRM, sites, legacy CRM/support, Catalogue/OEM and
customer stock/order implementations remain byte-for-byte integration baseline.

## Validation

- 29 Control Center tests passed with hash-verified locked dependencies and
  restricted runtime/source roles on local disposable PostgreSQL.
- 145 Billing tests passed; signed peer scope/environment/replay, no finance
  mutation and callback deduplication included.
- 639 existing frontend unit tests passed; multi-entry production build passed.
- 16 local Chromium combinations passed across 320/390/430/1440 and four themes,
  real staff API/PG fixtures, keyboard/focus, reduced motion, overflow and explicit
  loading/error/empty/stale fault cases.
- Existing Corporate UX browser workflow passed with real customer auth, stock,
  sales lifecycle, buyer history, responsive layouts and Control Center OFF.
- Prepared image built/imported as non-root, excluded test fixtures, retained
  Europe/Kyiv timezone support; TLS and artifact hash verification retained.
- Independent run 43682622139 on 55c10e16b4fc160157317410fb055376c0177a1e:
  staff-and-projections, Chromium/WebKit browsers, billing-compatibility and
  warehouse-regressions all successful. The Warehouse job selects 119 collected
  tenant/security, team, stock/order, bulk, OEM and Billing compatibility cases.
  Public run/job conclusions verified; authenticated logs/artifact XML not read.
- A broad local run returned 1019 passed, one existing opt-in 100k benchmark skip
  and six setup errors. It began while the Billing registration signature was
  still being edited and mixed an imported old caller with the new module.
  Not claimed as a clean full-suite pass. A fresh seven-test Global Billing run
  and the frozen-source independent Warehouse regression job passed. No tests
  were disabled, deleted or weakened.

The first expanded finance CI job lacked Git history for the existing legacy
compatibility assertion; fetch-depth:0 fixed the runner prerequisite and the
subsequent job passed. Local WebKit download was blocked, but independent CI
executed the complete Chromium/WebKit matrix without engine override or skips.

## Limits

MRR/churn/cash summaries unavailable until policy/complete data; bounded detail
pages are not global totals. No other product adapters or external messaging.
Source-deleted rows retain history/stale state; tombstone propagation deferred.
Railway service inventory/deployed SHA/flags remain unknown. Staging/production
not deployed or accepted. Draft creation itself remains blocked by GitHub API
egress in the task environment; no live authorization is implied by this PR.

Stacked base: feature/carpot-referral-onboarding at
fdaef3c638765ca845692727f90c9f140395891b, not the older main.
