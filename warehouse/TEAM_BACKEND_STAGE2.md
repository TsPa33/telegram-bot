# UX 5.8 Stage 2 — backend release audit and handoff

## Scope and status

Prepared from `e6191a85e1ee72f8839c475817949b60f53041b5` in the isolated
`/workspace/carpot-ux58-stage2` worktree. No new Team frontend, UX 5.5,
production bot, infrastructure settings or staging data are part of this package.
Local commit preparation is authorized; **push is not authorized** by this audit.
Local tests do not prove Railway deployment readiness.

## Architecture and security review

Existing `accounts.id` remains the workspace key for all historical owned rows.
Old accounts become DIRECTOR roots (`workspace_account_id IS NULL`); employees
are individual Account rows pointing to that root. Sessions identify the personal
Account. Server-derived Identity separates `workspace_account_id` and `actor_id`.
Every business lookup filters on the workspace, while new immutable operations,
order events and team events identify the actual actor. Client-supplied actor or
workspace overrides are rejected. Existing immutable history is not rewritten.

The 31-permission registry covers all 76 authenticated method/path pairs (79
registered API pairs including public auth routes), with unknown
routes denied. Director permissions are implicit; ADMIN can manage only MANAGER
accounts and cannot grant rights they do not possess. MANAGER cannot manage
roles. Field-level writes and nested response redaction enforce cost, financial,
audit and mutation rights on direct API requests, including cached replay results.
Sessions, secure-cookie/Origin/CSRF checks and password-change restrictions remain.
Each employee mutation reads current rights under an actor row lock; request
caches are checked after authorization and bind their keys to the actual actor.
Stock and order mechanisms remain the single ledger with existing row locks and
idempotency. No duplicate financial/sales ledger was added.

Audit corrections made in this package:

1. Employee creation now defaults OFF in **every** environment, independent of
   WAREHOUSE_ENV. Only explicit `WAREHOUSE_TEAM_CREATION_ENABLED=true` enables
   POST /api/v1/team. Readiness reports this flag; it does not enable creation.
   Blocking, reducing access and reset of existing members remain available.
2. Reactivating an inactive manager counts all retained rights as newly granted;
   an admin cannot revive broader privileges. Blocking/reducing those rights is
   still permitted, and a director may explicitly reactivate them.
3. Authentication locks the Account row until session creation commits. This
   serializes login with blocking/password reset, so an old-password login cannot
   create an unrevoked session after reset has completed.
4. A waiting employee mutation rechecks its session after obtaining the actor lock;
   an earlier identity-map object cannot revive a concurrently revoked session.
5. Test identity fixtures use actual UX 5.8 Account/Identity fields, preserving
   session/CSRF assertions and adding inactive/mandatory-password checks.
6. Only the Compose `tests` service mounts current backend and scripts read-only
   at /workspace/warehouse/{backend,scripts}. This preserves repository-relative
   backup safety checks and prevents testing stale image source. DB has no host
   port. No production Dockerfile was changed.
7. Route-coverage tests now recurse into FastAPI 0.143 lazy included routers.
   The old shallow app.routes loop could pass without checking any authenticated
   route. The revised test requires a nonempty expected-size inventory; a second
   test sends real HTTP requests to every permission-protected route as an
   activated employee with zero rights and verifies no business writes occur.

## Migration and compatibility

`a73e05b9c842 -> b94f62d18e07` is the sole Alembic head. Existing owners retain
IDs/password hashes and become active directors. Sessions, vehicles, parts,
quantities, reserves, orders, recorded financial amounts and immutable history
are preserved. Mutable stock/order request caches gain actor_id backfilled from
account_id, with fingerprints and response snapshots unchanged. No historical
sale prices or actors are invented. New FK/CHECK constraints and immutable
team_events trigger protect the new schema.

Upgrade is transactional; a 5-second DDL lock timeout aborts safely. A local
blocked-DDL regression verifies the old revision and data survive failure, then
upgrade/repeated upgrade succeed after the blocker is released. Empty/populated
upgrade, metadata consistency, validated FKs and existing cookies/request replay
are tested. This is not a benchmark for a production-sized request-cache table.

v5 Inventory, v6 Orders, v7 Workshop and v8 Smart Search remain available.
v8 schema checks accept the reviewed descendant head. v9 Team endpoint:
`GET /api/v1/team/readiness` (authenticated), required_revision=b94f62d18e07,
features: workspace_actor_separation, server_permissions,
live_session_revocation, financial_redaction, actor_bound_replay.
Stage 1 frontend gate compatibility is required **before** this migration.

Downgrade refuses once any employee or security event exists. Forward-fix is the
normal recovery path; rolling back only Docker code does not roll back schema.
Any database restoration must be separately authorized and use an isolated
verified backup; never stamp Alembic or improvise manual stock changes.

## Reproducible local tests

Use only an isolated warehouse*_test PostgreSQL. `db_test` uses tmpfs/private
Compose networking and no published PostgreSQL port. The existing tests image
supplies dependencies; mounts supply the actual worktree source and scripts.
Example (password supplied privately through environment, never committed):

```sh
docker compose -f warehouse/docker-compose.yml --profile test up -d --no-build --wait db_test
docker compose -f warehouse/docker-compose.yml --profile test run --rm --no-deps tests python -m pytest -q -o cache_dir=/tmp/warehouse-pytest-cache
docker compose -f warehouse/docker-compose.yml --profile test stop db_test
```

Team tests explicitly enable creation within their test fixture; separate tests
remove the flag to prove the API default fails closed in all environments.
Existing offline Plan.Parts tests use transport fixtures, never paid API calls.
No skips/xfails were added to conceal failures. The existing opt-in Smart Search
performance benchmark remains skipped. Physical Safari is not covered.

Final local evidence:

- Full backend pytest: **283 passed, 1 skipped**, zero failures. The skip is the
  existing opt-in search benchmark; the only warning is the pre-existing
  FastAPI/TestClient httpx deprecation.
- Targeted Team/security/migration audit: **23 passed** (included in the full count).
- Existing Stage 1 frontend production TypeScript/Vite build passed.
- Six old-frontend browser suites passed: workshop-gate, workshop, sales, orders,
  smart-search, ux561. Desktop 1440x1000/iPhone 390x844 were covered by all;
  workshop-gate/workshop/smart-search/layout also covered tablet 768x1024.
  The layout suite includes CSS zoom 125%/150%. No physical Safari claim.
- Empty/populated/repeated upgrade, blocked-DDL rollback/retry, existing session
  and request-key preservation, FK validation and Alembic metadata check passed.
- Python syntax, git diff --check, local Railway configuration and Watch Paths
  checks passed; package scanning with Gitleaks found no secrets.
- No Railway connection, live DB operation, real backup or push was performed.
  Local temporary containers were stopped/removed after checks.


## Railway configuration: expected versus observed

Repository configuration: root /warehouse, feature/carpot-warehouse-mvp,
`deploy/railway/backend.Dockerfile`, CMD `python -m app.staging`.
The unchanged entrypoint validates staging config, drops bootstrap privileges,
acquires a session advisory lock, runs Alembic successfully and **only then**
starts one Uvicorn worker on Railway PORT. Migration failure prevents serving.
Healthcheck is /health; private PostgreSQL service is postgres. Watch paths and
Docker COPY inputs pass local check-config.py/check-watch-paths.py checks.

Expected existing application service labels are telegram-bot (Warehouse backend)
and confident-sparkle (Warehouse web) in warehouse-staging. Older generic labels
warehouse-api/warehouse-web in templates are aliases, not instructions to rename
or create services. Do not modify production, DB credentials, volumes or origins.

Live state is **not verified**: this session has no Railway management connector
or authenticated Dashboard session; public HTTPS checks were rejected by the
network proxy (`Tunnel connection failed: 403 Forbidden`). This is a transport
failure, not an application readiness result. No deployment Active status,
staging schema revision, source branch, Auto Deploy state, Stage 1 deployed SHA,
Variables or verified backup was observed. No Railway CLI was used.

## Hard blockers before push / controlled rollout

A designated operator must verify, without changing production:

1. Correct existing project/environment and actual Warehouse services, feature
   branch, root, Dockerfile, start command, one worker/replica and Watch Paths.
   Auto Deploy must target only the Warehouse services. Do not use /warehouse/**
   as the shared watch pattern. Existing Stage 1 web deployment must be Active
   with e6191a8 compatibility (or a separately reviewed descendant).
2. Confirm the backend flag is absent or false; explicitly true is a blocker for
   Stage 2. Do not enable employees before Stage 3/4 approval.
3. Authenticate as an existing director, record the current schema revision and
   v5-v8 readiness. Obtain a current private staging PostgreSQL backup, SHA-256,
   pg_restore --list and a successful restore to separate test PostgreSQL per
   BACKUP_STAGING.md. A local test DB is not a staging backup.
4. Review DDL rights, free space, table size, outstanding transactions/locks,
   startup timeout and an approved quiet deployment window. Expect old backend
   instances to become unhealthy on a new migration head. Never assume atomic
   frontend/backend switching; drain old artifacts before enabling employees.
5. Obtain separate approval for push. Recheck origin still equals e6191a8;
   if changed, stop for review. Then use the non-force command from this
   detached worktree: `git push origin HEAD:refs/heads/feature/carpot-warehouse-mvp`.
6. Observe Auto Deploy logs: Alembic b94 completed before Uvicorn serving, correct
   artifact Active. With existing director session verify /health and authenticated
   readiness v5/v6/v7/v8/v9, sole database_revisions=[b94f62d18e07], and
   employee_creation_enabled=false. HTTP 401 without login is not readiness failure.
7. Smoke-check existing donors/stock/reserves, history, analytics, orders, Smart
   Search and login/logout. Use approved staging fixtures for any write checks;
   do not sell or alter real stock merely to test deployment.

If startup migration fails, inspect logs and lock blockers without exposing
credentials. PostgreSQL transactional DDL leaves the previous head/data on a
failed upgrade. Verify that explicitly; do not stamp/repeatedly force the head.
Only under new approval remove the blocker and retry via controlled publication.
After successful migration, prefer a compatible forward correction. Restoring
backup is a separate, explicitly approved maintenance procedure that accounts
for writes since the backup; do not automatically overwrite staging data.

## Stage 3 and Stage 4 handoff

The original full UX 5.8 remains preserved in /workspace/carpot-ux58. Stage 3 must
be isolated from the final Stage 2 commit and merge only frontend changes,
retaining Stage 1 gates and newer published fixes. Reconcile the new default-OFF
flag in UI messaging: ready schema is not creation permission/activation.

Stage 3: personal identity/role display and permissions context, Team roster with
pagination, employee create/edit/block/reset, permitted role delegation, temporary
password handling, mandatory password-change screen, actual audit actors, financial
redaction presentation and hidden/disabled unauthorized functions. Use real server
contracts and errors; no frontend substitute for authorization. Re-run old browser
regressions plus Team flows on desktop/tablet/iPhone viewports. Creation remains
OFF during publication and until every backend artifact is verified.

Stage 4, separately approved: verify private password delivery, enable only the
Warehouse backend creation flag, test Director -> Employee -> required password
change -> granted/denied actions -> block/revoke -> audit, including admin
reactivation restrictions and session/reset races. Recheck production isolation,
backups and all readiness contracts. Physical iPhone Safari requires an actual
device check; Chromium viewport tests do not claim it.

## Exact local release files (32)

- `warehouse/TEAM_BACKEND_STAGE2.md`
- `warehouse/backend/alembic/versions/b94f62d18e07_team_permissions.py`
- `warehouse/backend/app/api/checklists.py`
- `warehouse/backend/app/api/deps.py`
- `warehouse/backend/app/api/dismantling.py`
- `warehouse/backend/app/api/orders.py`
- `warehouse/backend/app/api/plan_parts.py`
- `warehouse/backend/app/api/routes.py`
- `warehouse/backend/app/api/secure_route.py`
- `warehouse/backend/app/api/smart_search.py`
- `warehouse/backend/app/api/team.py`
- `warehouse/backend/app/api/workshop.py`
- `warehouse/backend/app/main.py`
- `warehouse/backend/app/models/__init__.py`
- `warehouse/backend/app/models/orders.py`
- `warehouse/backend/app/permissions.py`
- `warehouse/backend/app/route_registry.py`
- `warehouse/backend/app/services/auth.py`
- `warehouse/backend/app/services/inventory.py`
- `warehouse/backend/app/services/orders.py`
- `warehouse/backend/app/services/team.py`
- `warehouse/backend/app/staging.py`
- `warehouse/backend/tests/test_dismantling_readiness.py`
- `warehouse/backend/tests/test_dismantling_v2.py`
- `warehouse/backend/tests/test_plan_parts_migration.py`
- `warehouse/backend/tests/test_quick_vehicle.py`
- `warehouse/backend/tests/test_smart_migration_permissions.py`
- `warehouse/backend/tests/test_staging.py`
- `warehouse/backend/tests/test_team.py`
- `warehouse/backend/unit_tests/test_plan_parts.py`
- `warehouse/backend/unit_tests/test_vehicle_lookup.py`
- `warehouse/docker-compose.yml`
