# Warehouse v3 Stage 1–2B: final local release audit

Audit date: 2026-10-28. **PASS — READY FOR STAGING RELEASE.** This is readiness for isolated staging, not production certification. No push, deployment, staging migration/preview/apply/backfill, Railway variable change, or Telegram-bot operation was performed.

## Git and release scope

Branch: `feature/carpot-warehouse-mvp`. Fresh `git fetch origin` confirms remote `069d5182c3163d660d3e50b429faf9b1da647855`, rather than the supplied previously known `133e9b9…`. Remote is an ancestor; a normal fast-forward is possible. All pending files are under `warehouse/`; worktree was clean before this report and is checked again after its local commit.

Pending implementation commits, oldest first:

- `133e9b90ef734b46faa2121b711dc8ac32aec9bb` import review draft UX.
- `d214ba16ee906b0a3b1e4a89ddcddda8568b5b5c` canonical Stage 1.
- `e3871a1e589e88a5608f26ea751d3dfb91724e4a` canonical documentation.
- `43b766719806134b94b990eb3ea22593eb4ecc10` verified Stage 1.5 coverage.
- `9ab958adc01437bf32e4f5212a48aa3ea3c8b0bd` configuration-aware Stage 2A.
- `d3ee249eecff51eea9edb00d161571fe71e753e9` managed Stage 2B.
- `dd9b80419d91647193cd1f21d422349cec4668ec` measured plan performance fixes and regressions.
- `f05bbc401f98c643263086b36712fedf3959edf5` financial fingerprint isolation fix.

The additional documentation commit containing this report is the final local HEAD; obtain its exact SHA with `git rev-parse HEAD`. Nothing has been published.

API `telegram-bot` and Web `confident-sparkle` are expected to Auto Deploy after a separately authorized push, per supplied staging configuration. Backend changes require API deployment and migration. Railway was not accessible in this session: actual service health, watch patterns and live database revision were not independently confirmed. Deployment templates must not be used to rename existing services.

## Migration and preservation: PASS

Exact upgrade chain from the supplied expected staging revision:

`41f9a2c87d10 -> 5c7d9e1a320f -> 76af12de4b90 -> 84d2c6fa190b`

One head: `84d2c6fa190b`. `alembic check`: no new upgrade operations. New reference/configuration tables, metadata JSON columns, replay table and a partial unique placement index are additive. There is no upgrade deletion of Aleto v1/v2 records, finance or audit, no automatic normalization/backfill, and no automatic stock creation. Canonical references are global rather than copied per workspace. Existing Part/Operation receipt flow remains authoritative; no parallel ledger was introduced.

[Populated upgrade evidence](populated-upgrade.json) uses real Volvo A (7,246 offers, 10,112 applications, 14,400 paths) plus synthetic stock, sale, reservation and legacy exclusions. It is **not a Railway database copy**. Every original table/column fingerprint matches after upgrade, foreign keys validate, the old 33-item plan remains accessible, and canonical types remain empty until explicit owner publication. A separate real application lifespan test starts twice with the queue worker enabled and verifies every table remains unchanged after both polls.

No destructive upgrade was found. Downgrade removes newly introduced metadata and is unsuitable as a routine rollback after v3 use. The user waived mandatory Railway backup as a release gate; a catalogue ZIP cannot restore stock operations, audit or manual decisions.

## Security and transactional workflow: PASS after fixes

Workspace isolation, RBAC, server-derived actor, CSRF, fail-closed platform-owner allowlist, audit history and preview confirmation remain enforced. Global canonical normalization/review uses the owner gate; ordinary workspace users cannot gain it through DIRECTOR or a catalogue permission alone. Financial fields remain protected.

A critical local regression reproduced a **cost-guess validation oracle**: the old public plan etag included a hash of a Part snapshot containing hidden unit cost. An API-only low-privilege client could reconstruct public fields and validate candidate costs. The fix selects only physical nonfinancial Part state (`id`, vehicle/category IDs, quantity, reserved quantity, archived). Neither cost nor selling price is fetched for this fingerprint. The adversarial regression now passes. No production exploitation or raw cost disclosure was observed or asserted.

The managed protocol version is now `carpot.managed-plan.2b.2`: old pending preview tokens/etags require a fresh preview (409), while completed replay keys continue to return their cached result without reapplying.

Preview is read-only. Save, exclusion and receipt require explicit commands. Vehicle locking, stale-token checks and persisted request keys prevent concurrent duplicate plans/receipts; injected failures roll back transactionally. Exclusions and historical decisions survive reload and configuration changes. Unknown equipment remains unknown. Sold/reserved/received parts are protected. Presence, dismantling and receipt are separate states.

Legacy plans remain readable. Ambiguous matches require manual one-to-one decisions; new generation does not silently merge unrelated manual stock. Old prepare/start is guarded once a managed plan is active. Existing unlinked manual stock still requires physical review rather than automatic deduplication.

## Measured performance: PASS

[Final measurements](managed-plan-performance.json) are local PostgreSQL service timings on synthetic preverified constructive slots, not real Volvo coverage, HTTP timings or Railway guarantees. Profiling preceded optimization. Main bottlenecks were per-row audit flushes and repeated legacy/state scans. The fix batches audit persistence while keeping every row event, indexes reconciliation and avoids redundant JSON encoding. Stock receipt uses the unchanged default audit flush behavior.

| Positions | Preview s | Save s | Repeat preview s | Repeat save s | Bulk exclude s | Peak RSS MiB |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 0.101 | 0.189 | 0.092 | 0.260 | 0.100 | 93.7 |
| 500 | 0.319 | 0.742 | 0.453 | 1.304 | 0.547 | 130.1 |
| 1,000 | 0.782 | 1.794 | 1.035 | 2.491 | 1.222 | 170.1 |
| 5,000 | 6.406 | 11.447 | 9.036 | 14.564 | 1.929 | 424.5 |

Bulk exclusion covers min(N, 1,000) positions; 5,000 is a backend stress case, not a typical dismantling or a 5,000-row phone rendering claim. RSS is process cumulative high water. SQL counts are SQLAlchemy execution callbacks including executemany batches, not individual row writes. At 5,000, save uses 61 executions/2 flushes versus baseline 10,055/5,002. All per-row audit entries are asserted present; no stock and no repeat duplicates are created.

[Unprofiled baseline at 5,000](managed-plan-baseline-5000.json): preview 9.862s, save 20.281s, repeat preview 41.148s, repeat save 50.513s. Local runs vary; final figures above include the financial fix. Reproduction is destructive only to an explicit disposable loopback database:

```sh
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_release_perf_test \
  python scripts/benchmark_managed_plan_v3.py --confirm-disposable \
  --sizes 100 500 1000 5000 --output /tmp/managed-plan-performance.json
```

## Volvo evidence and XC90: PASS within available inputs

Real A verified coverage remains 1,128/7,246 offers (15.57%), 75 canonical types and 1,444 constructive variants. Remaining source records are retained for explicit review, not silently confirmed. Stage 1.5 records 11,585 unprocessed records and 20 review records; these are records/paths, not an offer-count subtraction.

[XC90 test](xc90-real-A.json) uses real A with a synthetic 2020 donor and unverified trial engine facts. It proposes 168 candidates; the fixture explicitly skips 35 ambiguous candidates and saves 133. Switching petrol to diesel reuses those 133 with zero new duplicates and zero stock creation. This is not proof of physical fitment or a real decoded VIN. The Stage 2A evidence separately classifies 0 confirmed, 9 possible and 159 unknown positions.

Real B ZIP is absent locally and was **not tested**. [Synthetic B-shape evidence](synthetic-B-shape.json) exercises 10,222 offers / 14,324 applications / 29,922 paths, preserves old tables and repeats without new references. Its small synthetic vocabulary and 80% synthetic coverage must not be interpreted as real B coverage.

## Tests and packaging: PASS

- Full backend suite before the final localized financial fix: **469 passed, 1 skipped** (465.01s).
- After that fix: relevant release-audit and managed-plan suites **23 passed** (106.33s), including populated migration, startup, concurrency, rollback, protected stock, batching, real A and adversarial financial regression. These overlap the full suite; counts are not additive.
- Frontend: **349 passed**; production build passed.
- Final browser smoke against local authenticated API and production frontend: managed and read-only workflows pass at **1440px and 390px**. Includes lost-response retry with the same key, reload, bulk exclusions/restoration, explicit receipts, stale/protected operations, no auto prepare/start/receipt, no horizontal overflow or JS errors. This is Chromium viewport emulation, not physical iPhone/Safari certification.
- API and Web Docker builds passed. The restricted builder needed temporary proxy/CA build-secret adaptation outside the repository; TLS verification stayed enabled and repository Dockerfiles were not changed. Final API image smoke confirms 100 OpenAPI paths and nonfinancial protocol 2b.2; Web production image built successfully.
- Final `git diff --check`, single Alembic head and metadata/schema check passed.

Relevant regressions: `warehouse/backend/tests/test_v3_release_audit.py`, `test_dismantling_plan_v3.py`; browser scripts `managed-dismantling-browser.mjs`, `dismantling-preview-browser.mjs`.

## Remaining release considerations

No known local blocking defect remains. Live Railway revision/health and real B compatibility remain unverified here. Before any later authorized publication, re-fetch remote and stop on unexpected divergence. Allow API migration and both deployments to finish before v3 writes; avoid old/new API mutation overlap or rolling back an API after new writes without review. Existing pending v3 tokens must be refreshed after the fingerprint version change.

Migration does not publish canonical rules automatically. Until a separately authorized platform-owner preview/review/publish, v3 may expose only the 33 base positions; existing v2 B remains intact. Low real-A coverage is explicit and must not imply completeness. Actual staging B verification and physical fitment review remain later acceptance work. No catalogue import or apply is authorized by this audit.
