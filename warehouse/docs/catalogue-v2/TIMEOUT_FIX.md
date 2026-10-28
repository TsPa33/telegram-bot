# Catalogue v2 — durable operations and timeout fix

Local patch after release `760d5e2e8d7928df0e6bd55641294acbe311577b`. No push, Railway deployment, staging apply or production access. Real `CarPot_Volvo_10222_catalogue_v2.zip` and staging job `3b8eb380-e731-4f62-8545-c0336e015d7d` were not accessed or modified.

## Profile and cause

The old synchronous preview executed `Planner.run()` inside the HTTP request. Explicit flushes for new entities, offers and applications repeatedly flushed pending prices/paths too. A cProfile run on local PostgreSQL 16, 1 000 unique offers/rows, measured **3.825 s, 5 020 SQL calls, 3 009 flushes**; flush work occupied about 3.05 s. There was no SELECT-per-row loop; the bottleneck was repeated ORM write/flush round trips. The global catalogue advisory transaction lock also made subsequent preview/apply requests wait for the previous transaction.

The savepoint rolled back speculative preview inserts, but incurred their database work. Nginx's 60-second read timeout ended the client request without a durable HTTP operation status. A synchronous thread can continue after the proxy disconnects, including committing a preview report or an explicitly requested apply. A 504 alone therefore never established whether the server transaction completed.

## Implementation

The existing planner, identities, decisions, aliases, price observations and deduplication rules are reused. New rows are staged with the same deterministic IDs, then inserted in FK order in batches of 500. Existing objects flush once. Price history and paths load in batches only for offers in this job; the canonical entity/alias index remains global for manual matching. Preview uses the same planner with persistence disabled; its savepoint still rolls back any speculative changes to attached existing objects. It issues no global catalogue INSERTs. Apply enforces database constraints and remains one atomic transaction.

Same profiled 1k input after the final patch: **0.623 s, 9 SQL calls, one job-report flush**. `proxy_read_timeout` remains unchanged.

## HTTP and state protocol

Upload remains HTTP 201. Preview and explicitly confirmed apply now return **HTTP 202** with job metadata and `operation`:

```json
{"operation":{"id":"uuid","kind":"preview","status":"queued","progress":{"phase":"queued","done":0,"total":0},"error":null}}
```

Poll authenticated owner-only `GET /api/v1/catalogue/admin/jobs/{id}`. `operation.status` is `queued`, `running`, `done` or `error`; the existing job status is still `uploaded`, `review`, `ready`, `applied` or rejected-upload `failed`. A failed operation preserves the previous job/preview rather than discarding the uploaded file. Queue errors carry a concrete message; unknown database exceptions expose a safe message and are logged internally. Progress counts processed offers and the current phase; completing planning is not the same as committing apply.

A duplicate active command returns the same operation. A different command for the busy job receives 409. Concurrent submissions are serialized by a short try-advisory lock plus a partial unique active-operation index; submission never waits for the catalogue planner lock. Replaying a completed apply returns its completed operation, without another mutation. Apply still requires strict `confirm: true`, the stored preview token and matching catalogue revision/payload.

Frontend polls status, restores the selected job after reload, displays queue/progress/errors, disables duplicate actions and retrieves persisted state after an ambiguous request failure. Browser closure/disconnection does not cancel an accepted command. History also displays operation status.

## Worker coordination and restart

The API lifespan starts one background thread per process, with separate NullPool database connections. A PostgreSQL **session advisory worker lock** allows only one process/replica to execute queue work at a time; ordinary API requests do not occupy this thread or its connections. A second transaction lock fences work against recovery, including loss of the coordinator connection. Locks release on database connection/process death.

Only explicit persisted commands execute. There is no scanning/import of uploaded legacy jobs, bundled data, startup backfill or automatic catalogue apply. Queued commands retain the user's explicit request and may execute after restart, subject to fresh owner allowlist/account/session checks. Previously `running` commands become controlled `error` after old catalogue transactions release their lock. They are **not automatically retried**; the owner must explicitly preview/apply again. Successful operation completion commits in the same transaction as the job/catalogue changes, so a crash after commit cannot replay apply. A crash before commit rolls everything back. Progress is a separate small durable update; partial progress is not evidence of applied data.

Default worker execution is enabled. `WAREHOUSE_CATALOGUE_WORKER_ENABLED=false` is for controlled local tests/maintenance; requests remain queued while no worker is enabled. No Railway variables were changed. Platform owner allowlist, fail-closed access, CSRF, session authentication and workspace isolation remain enforced. Session identifiers are not returned in operation responses.

## Migration and release constraints

Additive migration `41f9a2c87d10` follows `021e8f6f220c`, creates only `catalogue_operations` and its constraints/indexes, and contains no data import. The chain from `b8716962f6b8` remains linear. Frontend readiness accepts the verified new head while retaining the previous UX 5.8.1 contract checks. Stock, sale prices, finances, audit and Aleto v1 tables are not modified by catalogue operations.

Backend and frontend must ship together because the POST response is now asynchronous. Before a separately authorized staging release: use the existing backup procedure, apply migrations through the normal startup path, check health/readiness and worker logs, then request preview explicitly. Existing uploaded job `3b8eb380-e731-4f62-8545-c0336e015d7d` is not automatically processed. Do not apply its catalogue without separate authorization.

## Synthetic performance

Local PostgreSQL 16, wall-clock seconds, same fixture generator with realistic offer/application/path ratios and 12 categories plus multiple subcategories. Measurements include service transaction commit and repeated-job checks, exclude upload/CSV conversion and queue scheduling; the benchmark executes the same service functions as the worker. cProfile baseline is a different 1k fixture (1k unique offers) and is compared only with its identical final-profile input above. Concurrent local regression work causes timing variation; these are not Railway latency guarantees.

| Input rows/paths | Unique offers | Model links | Preview | Repeat preview | Apply | Repeat apply | Peak RSS MiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 000 | 342 | 479 | 0.230 | 0.141 | 0.408 | 0.019 | 93.9 |
| 10 000 | 3 416 | 4 787 | 1.982 | 1.606 | 5.099 | 0.232 | 207.5 |
| 30 000 | 10 249 | 14 361 | 4.896 | 5.040 | 12.055 | 1.109 | 460.3 |
| 50 000 | 17 081 | 23 936 | 11.079 | 9.563 | 23.265 | 1.306 | 607.1 |
| 29 922 | 10 222 | 14 324 | 6.413 | 5.926 | 12.559 | 0.573 | 459.9 |

All stored counts were asserted; repeated preview returns the identical report and writes no catalogue; repeated apply produces no additional records. Full data: [timeout-benchmarks.json](timeout-benchmarks.json).

The canonical entity/alias index remains in memory to preserve global matching. Run a single coordinated worker with **at least 1 GiB available API/container RAM for 50k jobs**, plus headroom for ordinary traffic and catalogue growth. A 512 MiB limit is insufficient for the measured 50k fixture; even the exact-volume synthetic fixture reached about 460 MiB without ordinary traffic. This resource prerequisite must be checked before a large staging import. Runtime limits were not changed.

Real Volvo B was unavailable; the 10 222/14 324/29 922 fixture is explicitly synthetic, not a test of its actual schema, resolutions, prices or deltas.

## Reproduce locally

Tests erase data: use a dedicated loopback PostgreSQL `warehouse*_test` database only.

```bash
cd warehouse/backend
export WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_catalogue_v2_suite_test
python -m pytest tests/test_catalogue_jobs.py tests/test_catalogue_v2.py tests/test_catalogue_release_audit.py tests/test_aleto_catalogue.py tests/test_ux581.py -q
# Separate disposable perf DB, migrated to head before running:
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_catalogue_perf_test python scripts/benchmark_catalogue_jobs.py --rows 50000 --confirm-disposable
```

`benchmark_catalogue_jobs.py` rejects non-loopback/non-test database names and requires explicit disposable confirmation. It truncates only that test database and generates synthetic data.

## Validation results

- Focused catalogue/queue/v1/UX 5.8.1 backend run: **75 passed** (50.60 s).
- Broader backend run: **279 passed, 1 skipped**, six assertions expected the previous head `021e8f6f220c` instead of new `41f9a2c87d10`. These were test expectations, not application/migration failures. After updating them, the affected migration/readiness suites plus all queue regressions (including one newly added concurrent HTTP test) passed: **56 passed** (45.56 s). The opt-in 100k search benchmark remains skipped. No known failed check remains; the 75/56 runs overlap and are not added together.
- Queue tests cover durable acceptance, same-command replay, conflicting commands, concurrent submissions, independent worker exclusion, ordinary API responsiveness, browser disconnection, killed preview/apply processes, explicit retry, coordinator connection loss, revoked allowlist/session, all-or-nothing bulk failure, and a SQL-count/no-speculative-preview-write guard.
- Existing tests cover preview SHA/token/revision, immutable prices, aliases/manual mappings, repeat/increment, CSRF/file bounds, other-workspace denial, full real A, and fingerprints of original stock/sales/finance/audit tables.
- Frontend: **215 unit tests passed** (team 53, smart search 65, workshop 97); TypeScript/Vite build passed.
- Real local browser/API test passed at **1440px and 390px**: owner upload, asynchronous preview, reload, explicit mapping/apply, shared read, and non-owner denial. Real B was not used.
- Sole Alembic head and populated-DB migration roundtrip/`alembic check` passed. `git diff --check` passed.

The code is ready for a separately authorized isolated staging release. Large-import validation still requires adequate RAM and the actual ZIP; no staging or production operation has been executed by this patch.

Final API snapshot-order correction: status is read before the job so a terminal operation cannot be paired with a pre-commit job snapshot. After this correction, the complete catalogue/queue/release-audit set passed again: **46 passed** (38.01 s).
