# CarPot Billing Phase 2.1 stabilization

Base: Phase 2 `1f288f038e93f05e76a605104be71dab296b6219`. Branch: `fix/carpot-billing-phase2-stabilization`. No deployment, live data, Railway configuration, payment/provider invocation or Phase 3 work.

The release gate is **pending**, until the full independent CI finishes with zero failures. A successful subset does not imply readiness. [All original 44 failures](failure-classification.md) are classified individually; the historical baseline evidence remains [run 43305563188](https://github.com/TsPa33/telegram-bot/actions/runs/43305563188).

## Production corrections

- Revalidate every mutation session after acquiring the workspace lock, including directors. The event-based regression intercepts the actual identity lock boundary. Verify both feature flag settings.
- Worker actor KEY SHARE avoids conflicting with writer NO KEY UPDATE; session SHARE, queue/advisory claim and publication coordination remain intact. Workspace writer serialization remains exclusive between writers. Search GET takes no workspace row lock.
- Correct the language false positive for Ukrainian «Головна передача». Strong Russian signals remain reviewable. Distinct constructive details are not duplicate type names.
- A fresh, uncommitted batch receipt scope avoids repeated assembly lookups only for newly minted part IDs, verifies receipt/zero-stock preconditions and is always cleared in `finally`. Existing parts retain all guards.
- Vehicle physical/registered counts share one filtered aggregate.
- Additional Phase 2 audit found a quota bypass through stale ORM identities: another transaction could restore a cached archived donor before a new vehicle flush. Usage now reads committed scalar columns and overlays pending changes, preserving both fresh data and unsaved mutations. The regression fails before this fix and passes after it.

## Migration and contract infrastructure

Historical migrations are unchanged. Historical tests now create UUID-named disposable loopback `*_test` databases at their actual parent revisions, seed synthetic VIN, stock, sale, reservation, order and audit history, and copy compatible columns from their original domain fixtures with constraints/triggers enabled. Forward upgrade runs twice; every original table/column is compared exactly and Alembic metadata check runs at HEAD. Only the newly created historical database is dropped.

The staging `08b72c9d4e16` → packaged Phase 2 HEAD `a12b34c56d78` case retains real bundled Volvo A source counts (7246 offers / 10112 applications / 14400 paths), synthetic physical history, legacy exclusions and validated foreign keys. This is not a copy of live staging data. Unknown acquisition date, durable pricing decisions, virtual inventory, runner/adapter/PartLine queue history, VIN evidence and populated entitlement projection downgrades are independently refused at their immediate migration boundaries. Failed smart-search upgrades verify transactional rollback and successful retry on index conflict and real table lock.

Intentional API changes are asserted explicitly: private exact-source count is absent publicly and equals one through real platform-admin preview; manual OEM provenance records the actor while all other stock/sale fields stay unchanged; engine label is separate from structured engine code; ETag includes VIN evidence, engine code and drive while excluding private costs; missing generator is explicit null; current revisions come from packaged migration heads.

Large catalogue fixtures explicitly review every 200-issue page, accumulate decisions, re-run the actual planner and use fresh tokens. No production preview/review safeguard is bypassed. Offline router unit stubs implement the new scalar revalidation queries; per-case provider fixture caches are isolated to avoid reused mock transport IDs contaminating cases.

Browser fixtures follow current UI contracts. The obsolete quick-sale UI has been replaced by real order checkout; seller assertions retain Unicode/OEM/article search, prices, transfer/writeoff audit, single sale despite double-click/lost response, last-unit replay and distinct keys for new receipts. Sidebar alignment waits on actual layout convergence; the lost-response intake case waits for the injected response-loss event, rather than racing a heavy 227-item command against a 5-second alert assertion. Product UI is unchanged.

## Audit coverage

`test_entitlements_phase2.py` covers canonical/tenant binding, transport replay and scope, temporal downgrade/add-on expiry, single-use trial and concurrent claims, immutable grace deadline, donor provenance, archive/restore, global/VIN entry points, last garage place, team concurrency, expired old-order completion without expansion, dry-run and flags OFF. New tests cover snapshot expiry/downgrade concurrent with a pending vehicle mutation and search availability, plus stale cached donor restore. Finance additionally verifies eight concurrent snapshot publications produce distinct monotonic versions on one canonical company binding.

Source audit of `warehouse/backend/app` found no bulk SQL insert/update/delete targeting Account/Vehicle/Part/Order that bypasses the ORM quota guard. Catalogue bulk inserts target catalogue data; stock entry paths construct ORM Parts/Vehicles and flush through the guard. Legacy bot tables are a separate system and remain unchanged.

## Verification and limitations

- Finance: 55 PASS on fresh Docker PostgreSQL, including the original 54.
- Frontend: 631 PASS; production build PASS (existing bundle-size advisory remains).
- Additional entitlement audit: 18 PASS. Security/worker flags OFF+ON and snapshot/ETag/OEM regression subset: 10 PASS.
- Local complete discovery (`tests` + `unit_tests`): 998 PASS / 4 FAIL / 1 existing SKIP before final test-infrastructure corrections. All four failures are covered by a subsequent 29 PASS targeted run. A final independent full run is still required.
- Browser suites: corporate, current seller checkout (1440/390), integrated dismantling, mobile v2.3 Chromium/WebKit (320/390/430/1440), and Billing Chromium/WebKit × those widths × Gold/Forest: PASS locally. Product UI is unchanged.
- Five additional immediate-boundary forward-only history refusals: PASS.
- Eight focused historical/negative migration tests including populated real A: PASS. Complete local run passed the other historical cases; final import-runner packaged-head expectation is fixed and retested.
- The existing single skip is `test_smart_search_perf.py::test_scale`: explicitly opt-in 100k-row benchmark (`WAREHOUSE_SMART_PERF=1`), unchanged. It is separate from the measured mandatory batch/query regressions. No new skip, xfail or failure waiver is added.

The release workflow now runs current full backend including offline unit tests, finance, frontend/build, billing browsers, corporate and integrated sales/dismantling/mobile browsers. The old intentionally-red immutable Phase 1 diagnostic job is retired from the current-code release workflow: that historical comparison already has permanent evidence above. No current-code test is removed; no failure is made optional.

## Rollback

Do not downgrade financial, VIN or stock history. Before any future separately authorized rollout, retain a tested database backup and the previous deploy artifact. Roll back application code/feature flags while preserving all rows and receipts. If a migration requires correction, apply a reviewed forward migration. This PR does not deploy or activate enforcement for users. Phase 3 remains unapproved until the independent release gate is green and separate user authorization is given.
