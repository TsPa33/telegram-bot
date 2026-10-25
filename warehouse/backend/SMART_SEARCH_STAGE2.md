# UX 5.7 Stage 2 — backend preparation (not a deployment authorization)

Isolated worktree: `/workspace/carpot-ux57-stage2`, base
`c130608f07b01e55d282084997f63c2e5a9f8188`. No Smart Search frontend is included.
Stage 1 WorkshopGate and UX 5.6.1 are inherited unchanged. Original UX 5.5 and
full UX 5.7 worktrees remain untouched. No Railway operation, commit or push
was performed. The local results below do not establish Railway permissions,
backup availability, deployment settings or readiness.

## Backend contract

Authenticated read-only routes:

- `GET /api/v1/smart-search/parts?q=...&vehicle_id=...&manufacturer=...&model=...&in_stock=true&offset=0&limit=50`
- `GET /api/v1/smart-search/readiness`

Legacy `/api/v1/parts` is unchanged. Smart Search requires the authenticated
account on every Part and Vehicle scope. It reads actual inventory; no generated
catalogue, fitment assumptions, price conversion, sale or reservation mutations.
`in_stock=true` means `quantity - reserved_quantity > 0` and not archived.
Parameterised SQL performs candidate selection, ranking, count and pagination.
The response contains Part snapshots, actual donor, available quantity, integer
ranking tier, truthful explanation and total. Equal ranks use Part UUID ordering;
pagination is stable against unchanged data, not a cross-request snapshot.

NFKC/transliteration normalization and the versioned local dictionary support
reviewed synonyms, donor words, explicit year and directional constraints.
Unknown alphabetic words of at least five letters may use pg_trgm; directional,
numeric and identifier distinctions are protected. Identifier normalization is
separate and never rewrites stored OEM/article values. Ambiguity returns a
clarification. Limit: 160 characters, 12 raw tokens, 8 meaningful groups,
100 results, offset <= 100000. `statement_timeout=2500ms` applies to each SQL
statement, not the entire HTTP request; max observed query count includes auth.
There is no index creation or background indexing on a search request.

Readiness v8 requires the sole installed Alembic head `a73e05b9c842`, pg_trgm,
both normalization functions callable, and **all six valid indexes**. Features:
`tenant_ranked_parts`, `direction_constraints`, `dictionary_aliases`,
`bounded_typo_search`. Unauthorized readiness is 401; missing capabilities/schema
are 503. An anonymous 401 is not evidence of authenticated readiness.

## Migration audit

`a73e05b9c842` follows `d86f21a90b34` without a branch or merge. Upgrade order:

1. `SET LOCAL lock_timeout = '5s'`.
2. `CREATE EXTENSION IF NOT EXISTS pg_trgm`.
3. Frozen IMMUTABLE/PARALLEL SAFE text and identifier normalization functions.
4. Part FTS GIN; Part trgm GIN; tenant+OEM; tenant+article indexes.
5. Vehicle model FTS GIN and tenant+brand index.

Index names: `ix_parts_smart_fts`, `ix_parts_smart_trgm`,
`ix_parts_smart_oem_number`, `ix_parts_smart_article_number`,
`ix_vehicle_smart_model`, `ix_vehicle_smart_brand`.
No table/column changes, DML backfill, inventory deletion or data rewriting.
Index contents consume additional disk/CPU and are maintained on writes.
Normal CREATE INDEX is transactional and can block writes until commit. It is
not CONCURRENTLY. A quiet window and adequate free disk are required. The 5s
lock timeout bounds lock acquisition, not the duration of index construction.

Alembic records the head transactionally. Re-running `upgrade head` at the head
is a no-op. Raw migration SQL is deliberately not a general-purpose idempotent
script: pre-existing unknown functions or same-name indexes fail rather than
being silently adopted. The extension installation alone uses IF NOT EXISTS.
Downgrade removes the six indexes and two owned functions, never pg_trgm (which
may predate Warehouse). Frozen function changes after release need a new
migration and index rebuild; do not replace an IMMUTABLE body under old indexes.

Local failure tests cover missing database CREATE privilege, a late index-name
conflict and a table lock. Failure leaves the old Alembic head, no partial Smart
Search functions/indexes, and unchanged Part/Operation rows. A retry after fixing
the cause succeeds. Local non-superuser extension installation succeeds with
schema CREATE/USAGE, database CREATE, owned tables and the trusted pg_trgm package.
This is tested on PostgreSQL 16, not a proof of a managed Railway policy.

## Required read-only Railway preflight (not executed)

An authorized operator must use an already approved private SQL access channel
for the **postgres service in warehouse-staging**, never the production database.
Do not expose a TCP Proxy, log connection strings or change Variables here.
The agent has not used Railway CLI. No new service/storage is authorized.

```sql
BEGIN READ ONLY;
SELECT current_database(), current_user, current_setting('server_version'),
       current_setting('server_encoding');
SELECT version_num FROM public.alembic_version ORDER BY version_num;
SELECT rolsuper,
       has_database_privilege(current_user, current_database(), 'CREATE') AS db_create,
       has_schema_privilege(current_user, 'public', 'CREATE') AS schema_create,
       has_schema_privilege(current_user, 'public', 'USAGE') AS schema_usage
FROM pg_roles WHERE rolname = current_user;
SELECT name, default_version, installed_version
FROM pg_available_extensions WHERE name='pg_trgm';
SELECT version, superuser, trusted
FROM pg_available_extension_versions WHERE name='pg_trgm';
SELECT extname, extversion FROM pg_extension WHERE extname='pg_trgm';
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner,
       pg_has_role(current_user,c.relowner,'USAGE') AS owner_role
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relname IN ('parts','vehicles');
SELECT n.nspname,p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.proname IN ('warehouse_search_text','warehouse_search_code');
SELECT schemaname,indexname FROM pg_indexes WHERE indexname LIKE 'ix_%smart_%';
COMMIT;
```

Expected pre-migration revision: only d86f21a90b34. Require UTF8 and supported
PostgreSQL normalize(), extension availability, owner-role access for the target
tables and function/schema creation. If pg_trgm is absent, extension installation
requires permitted database CREATE plus a trusted extension on this server,
or a separately approved DBA action. If it is installed, DB CREATE is not by
itself required, but the remaining DDL privileges still are. A read-only check
cannot prove DDL permission under every provider restriction: resolve ambiguity
with the database administrator before authorizing the automatic migration.
Do not grant superuser or install pg_trgm on staging as part of this preparation.
Check actual table ownership/schema/search_path and unexpected same-name objects.

## Backup and recovery plan

Before a future migration approval, agree on a quiet window, stop concurrent
writes for the backup/rollback decision window, and identify a verified backup
channel. No current staging backup is claimed. See `../BACKUP_STAGING.md` and
existing scripts. Those scripts require PostgreSQL 16 and exact Warehouse DB
identity; if the real server differs, stop and prepare compatible tooling.

Desired artifact: `pg_dump --format=custom --no-owner --no-acl` of the private
Warehouse DB only, plus source Alembic revision, SHA-256 and counts. Use a private
temporary directory in the existing approved container, not an API persistent
volume. Do not print credentials or pipe binary data through a text terminal.
Transfer must use the already verified authenticated transport, or separately
approved private TLS storage and short-lived credentials; do not invent a
Dashboard download capability or provision storage. The existing CLI launcher
is documented in BACKUP_STAGING.md but is not run or required by this task.
If no permitted transport is available, actual backup/release remains blocked
until a channel is explicitly approved.

On the local copy, verify sidecars and SHA-256, `pg_restore --list`, and full
payload decompression. Existing verifier:

```sh
python3 warehouse/scripts/verify-backup.py /PRIVATE/DIR/warehouse-staging.dump --docker
```

Restore only into a fresh disposable local PostgreSQL of a compatible major
version using `pg_restore --exit-on-error --single-transaction --no-owner --no-acl`.
Compare source revision, table counts, stock sums and audit/order records; run
application read checks against that restored copy. A successful `--list` or
checksum alone does not prove restorability. Keep the accepted backup private,
outside Git; delete temporary remote data only after verified retrieval/restore.
Never restore into the live staging DB as a test.

On failed automatic migration: the new API must not start; inspect the failure,
check actual head and object state read-only, fix the cause under separate
approval and retry. Do not stamp the revision or ignore an error. Startup uses
existing `python -m app.staging` -> advisory-lock-protected Alembic upgrade ->
Uvicorn. A migration exception propagates before socket binding. The startup
120s default bounds connection/advisory-lock waiting, not index-build runtime;
confirm actual Railway healthcheck/deployment timeout and resource limits.

If migration succeeds but the new backend fails, prefer a forward fix while
keeping UX 5.6.1. **Rolling Docker code back alone does not roll schema back**;
old migration graphs do not recognize a73e05b9c842. If an approved rollback is
necessary, stop writers, use the NEW artifact that knows the migration to run
`alembic downgrade d86f21a90b34`, verify data/head, then roll back the backend.
That operation is not authorized now. Do not remove pg_trgm. If restore is
needed for corruption, isolate the target and reconcile every post-backup sale,
reservation and audit event; do not overwrite newer inventory blindly.

## Future publication sequence (separate approval required)

1. Verify current origin, preserved worktrees, running frontend build includes
   Stage 1 + UX 5.6.1, live contracts v5/v6/v7 and exact d86 head.
2. Complete privilege/disk/timeout/backup preflight above; obtain release approval.
3. Publish only the reviewed Stage 2 backend. Existing Auto Deploy runs migration
   before serving; do not assume zero downtime or concurrent frontend deployment.
4. In Dashboard confirm the backend deployment SHA and Active status. As an
   authenticated user, request `/api/v1/sales-workspace/readiness` (v5),
   `/api/v1/orders/readiness` (v6), `/api/v1/workshop/readiness` (v7) and
   `/api/v1/smart-search/readiness` (v8). All should report the sole installed
   head a73e05b9c842; v7 required_revision stays d86f21a90b34 (minimum schema),
   whereas v8 required_revision is a73e05b9c842.
5. Check standard search and existing Workshop sale/notes/order flows, then
   authorized GET Smart Search examples and cross-account isolation. Confirm
   six valid indexes; retain the accepted backup.
6. Stage 3 frontend needs its own approval after v8. Its local old WorkshopGate
   diff must NOT overwrite the strict Stage 1 gate or UX 5.6.1 layout changes.

## Local evidence

The preparation runner uses disposable PostgreSQL 16 containers, loopback ports
and *_test databases. The permission tests create/drop extra disposable roles
and databases and require a LOCAL test superuser; do not point tests at Railway.
Performance test is opt-in with WAREHOUSE_SMART_PERF=1. It records 503 timeouts
explicitly rather than treating them as successful searches. Do not claim a
100k SLA or arbitrary multi-tenant/concurrent scalability from this benchmark.

Status: **PARTIAL**. Backend implementation and local compatibility/migration
checks pass. This does not authorize a push. Remaining release prerequisites:
Railway privilege/extension/ownership/disk/timeout and backup verification;
100k broad-query latency and bounded 503 outcomes must be accepted explicitly
or optimized before claiming consistently fast Smart Search.

Final checks:

- Full backend suite: **172 passed, 1 opt-in benchmark skipped**.
- Separate expanded benchmark: **1 passed as a measurement/safety test**, with
  three 503 responses explicitly recorded at 100k. This is not an all-success
  latency benchmark. An initial strict 200-only benchmark failed at 100k on
  `правий задній ліхтар`; the measurement continuation preserves that finding.
- Six browser suites against the NEW backend + UNCHANGED UX 5.6.1 frontend:
  UX561, WorkshopGate, Workshop, Sales, UX5 and Orders, all passed.
- Desktop 1440x1000, tablet 768x1024, iPhone viewport 390x844 (orders/sales/UX5
  desktop + iPhone; Workshop/Gate/layout all three). Physical Safari untested.
- Frontend baseline production build passed; no frontend source changes.
- Python AST syntax: 60 files; dictionary JSON and git diff --check passed.
- Local empty upgrade, populated upgrade, upgrade head repeat, downgrade/upgrade,
  Alembic check, advisory-lock/failure behavior, non-superuser permissions,
  incomplete-index readiness and authenticated v5/v6/v7/v8 passed.

Measured in-process TestClient HTTP including auth/serialization/tracemalloc,
PostgreSQL 16, single synthetic account/donor, ten query families x three samples,
limit 20. Other local checks overlapped. These are not Railway response promises.

| Parts | HTTP median ms | Worst ms | Exact OEM median ms | HTTP 503 / 30 |
|---|---:|---:|---:|---:|
| 1,000 | 56.97 | 111.13 | 39.53 | 0 |
| 10,000 | 151.76 | 606.58 | 21.39 | 0 |
| 100,000 | 834.86 | 4022.40 | 48.92 | 3 |

At 100k, `правий задній ліхтар` had [200,503,503] (median 4001.63ms),
`радіаторт охолоджентя` [200,200,503] (median 3546.37ms). The per-SQL timeout
is 2.5s; a complete HTTP request can exceed that while running multiple SQL
statements. Exact OEM, synonyms, simple typo, positive front and negative
left/rear constraints were also exercised. Negative direction queries return
zero, never the opposite-side records. Max SQL count: 8 including auth.
Peak traced Python allocations at 100k: 1.29 MiB; whole test-process peak RSS
161.20 MiB includes fixtures/imports, not isolated API memory or PostgreSQL.
All Part indexes together: 52.99 MiB at 100k, including pre-existing indexes.
Populated upgrade at 100k: **4206.10ms**, counts, stock/reserved sums and row hashes
unchanged. Separate functional tests preserve full Part and Operation snapshots.

Actual EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON), no forced planner settings:

```text
Exact OEM count: 0.101 ms
  Aggregate -> Bitmap Heap Scan parts (1 actual row)
    BitmapOr -> ix_parts_smart_oem_number + ix_parts_smart_article_number
Identifier preflight: Index Scan on the same tenant+identifier indexes.

правий задній ліхтар count: 1342.583 ms
  Aggregate -> Bitmap Heap Scan parts (20,000 actual rows)
    Bitmap Index Scan ix_parts_smart_fts (20,000 candidates, ~13ms)

радіаторт охолоджентя count: 851.183 ms
  Aggregate -> Gather -> Aggregate -> Bitmap Heap Scan parts
    BitmapOr -> identifier indexes + FTS + ix_parts_smart_trgm
```

Indexes are used, but broad matches still require expensive filtering/counting
and ranking. Count plans do not isolate every page-sort CPU cost. Raw local
measurement/plans: `/tmp/warehouse-ux57-stage2-perf.json` (not a release file).
No concurrent multi-tenant SLA, arbitrary dictionary coverage or production-size
Vehicle lookup scalability is asserted. Further query-plan optimization is a
known follow-up, not hidden by increasing the SQL timeout.

### Exact Stage 2 file set

All paths below are relative to the repository root. No frontend, Dockerfile,
Railway config, dependency lockfile, backup artifact or UX 5.5 file is changed.


- `warehouse/backend/SMART_SEARCH_STAGE2.md`
- `warehouse/backend/alembic/versions/a73e05b9c842_smart_search.py`
- `warehouse/backend/app/api/smart_search.py`
- `warehouse/backend/app/main.py`
- `warehouse/backend/app/models/__init__.py`
- `warehouse/backend/app/search/normalize.py`
- `warehouse/backend/app/search/query.py`
- `warehouse/backend/app/search/service.py`
- `warehouse/backend/app/search/terms.json`
- `warehouse/backend/tests/test_dismantling_readiness.py`
- `warehouse/backend/tests/test_dismantling_v2.py`
- `warehouse/backend/tests/test_plan_parts_migration.py`
- `warehouse/backend/tests/test_quick_vehicle.py`
- `warehouse/backend/tests/test_smart_migration_permissions.py`
- `warehouse/backend/tests/test_smart_normalizer.py`
- `warehouse/backend/tests/test_smart_search.py`
- `warehouse/backend/tests/test_smart_search_perf.py`
- `warehouse/backend/tests/test_staging.py`
