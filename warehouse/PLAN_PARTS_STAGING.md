# Plan.Parts: staging verification and recovery

This is an operator runbook, not authorization to deploy or migrate. All commands
below are for Warehouse only and require separate approval before changing staging.
Never select CarPot production. No provider requests are needed for migration,
health, manual-vehicle or security checks.

## Local preflight evidence — 2026-10-21

- Reviewed 27 Git-eligible modified/new files; every path is inside warehouse/.
  No files are staged. Gitleaks v8.24.2 found no secrets in those candidates.
  No real .env, certificate/private key, database file or generated build/cache
  is Git-eligible. Ignore checks cover application .env files, local TLS keys
  and frontend dist. Fixtures contain catalogue data, not user accounts/credentials.
- 88 backend tests passed on a disposable localhost-only PostgreSQL, removed
  afterward. Coverage includes real exported responses, auth/CSRF/Origin/rate
  limits, initial migration chain, preserved donor/audit data, NULL K-Type,
  repeatable staging migration startup and Alembic schema consistency.
- Production React build passed. Browser checks passed at desktop and iPhone
  viewports; all provider responses are offline fixtures, not paid API calls.
- Both Dockerfiles passed Docker --check without warnings; nginx -t passed as
  user nginx using the staging config and a long Railway-style hostname.
- The local Railway configuration checker passed. These checks do not establish
  actual Railway settings, resource availability or successful remote image builds.
  At preflight the integration was uncommitted/unpushed. Before rollout verify
  that the reviewed integration commit is present on the remote feature branch.

First rollout recommendation: provider disabled, backup existing staging data,
deploy DB → API → web after approval, verify b72f03d8e196 and /health, then test
manual vehicle creation. License review and separate approval for paid calls
remain prerequisites for enabling Plan.Parts. No live service was changed.

## Readiness gate

The user-supplied ZIP exports have been added to backend/tests/fixtures and replayed
through the client using MockTransport: 708 brands, 292 VW models, 35 Golf IV
modifications. The fourth export contains 632 Volvo category types and is validated
offline and supports explicit, account-local checklist import; see PLAN_PARTS_CHECKLIST.md.

Confirmed envelope: success=true, data.count, data.results; model selector data.mfa_id,
modification selector data.ms_id and data.limit. Model-name field: name. Dates are
YYYY-MM; 76 model year_to values are null. Parser rejects success=false, count/selector
mismatches and partial results, without automatic paid pagination. Counts are fixture
assertions, not hardcoded limits on future catalogue sizes.

Dates normalize to inclusive years. Null start is excluded when filtering; null end
means no known upper bound, not proof of current manufacture. Do not infer a provider's
complete null semantics or license permissions from these examples. License permission
and explicit approval for a limited live test remain prerequisites before enabling
PLAN_PARTS_ENABLED. No paid calls are necessary for fixture or migration verification.

## Target and source checks

1. Select the EXISTING Railway project and its empty-origin `warehouse-staging`
   environment. Verify only Warehouse services are targeted. Do not duplicate or
   synchronize production or change shared project/production variables.
2. Verify the reviewed integration commit is published on the GitHub feature
   branch before an authorized deployment. Do not deploy an older branch commit
   without the integration. Record exact current/rollback commit IDs.
3. API source: feature/carpot-warehouse-mvp, root /warehouse, Dockerfile
   deploy/railway/backend.Dockerfile; start python -m app.staging; PORT=8010;
   health /health, timeout 180 seconds; one worker/replica, no public API domain.
4. Web source: same branch/root, deploy/railway/frontend.Dockerfile, default
   entrypoint, PORT=8080, public target 8080, health /health, timeout 180 seconds.
5. Keep the dedicated Warehouse DB/volume private. Never change its initialized
   credentials or POSTGRES_DB as part of this rollout.

## Variables — check in Warehouse service scope only

Keep all existing WAREHOUSE_DB_* reference variables, WAREHOUSE_ENV=staging,
WAREHOUSE_COOKIE_SECURE=true, WAREHOUSE_REGISTRATION_ENABLED=false,
WAREHOUSE_STARTUP_TIMEOUT=120 and the private-proxy trust settings unchanged.
Both services need the same exact HTTPS WAREHOUSE_PUBLIC_ORIGIN without trailing
slash. Frontend WAREHOUSE_BACKEND_ORIGIN must resolve to the actual Warehouse API:
http://telegram-bot.railway.internal:8010 is valid ONLY if that service is the
isolated Warehouse backend in this environment, not the production bot. Otherwise
use the existing verified Warehouse service reference; do not rename services.

Before the first migration/manual smoke test set, after approval:

```dotenv
PLAN_PARTS_ENABLED=false
```

Only the API needs Plan.Parts variables. Once license/paid-test gates are satisfied and
live calls separately approved, use private API service variables:

```dotenv
PLAN_PARTS_ENABLED=true
PLAN_PARTS_API_KEY=<enter securely in Railway; never paste into commands/logs>
PLAN_PARTS_MODEL_NAME_FIELD=name
```

No VITE variable, frontend secret, persistent API cache or public DB is required.
Attempt limits are per process and reset on restart: 10/account/minute,
60/process/minute; identical account+selector requests suppressed for 60 seconds.
These are not token/billing caps. Configure provider-side spend controls before
allowing live use. There are no automatic retries.

## Backup and preflight — after approval, before API deployment

Use the dedicated Warehouse DB service's approved backup/export procedure.
Create and verify a consistent snapshot/custom-format pg_dump, store the backup
encrypted outside the deploying API container, and verify its contents with
pg_restore --list. Record timestamp, DB name, revision, row counts and backup
location without logging credentials. Include all Warehouse tables, sequences,
constraints and the immutable-audit trigger. Do not use a CarPot production DB.
Confirm a restore on an isolated disposable PostgreSQL before relying on it.

**Fresh first deployment:** there is no existing API container or Alembic revision
to inspect. Verify in the dedicated Warehouse DB service that this is the new,
empty `warehouse_staging` database, never a production database. Once approved,
deploy the DB first and let `python -m app.staging` apply the full chain:
eb8fddfe982f → f482ab1376c0 → c91e72b6a410 → a84d2c19e705 → b72f03d8e196. Never stamp an empty database.
Reserve the frontend HTTPS domain before API startup and set both public origins;
if Railway cannot reserve it before a first deployment, use the explicit temporary
origin procedure in RAILWAY_STAGING.md, then set the real domain before login.

**Existing Warehouse upgrade:** take the verified backup above. Inside the CURRENT
Warehouse API container (Railway service SSH, /app), read:

```sh
python -m alembic current
python -m alembic heads
```

The pre-integration image and DB should both report f482ab1376c0. In the new image,
heads reports b72f03d8e196 even before upgrade; it describes packaged migrations,
not the current DB revision. If c91e72b6a410 is already applied, startup applies
the checklist and nullable-date revisions. If a84d2c19e705 is applied, only the
nullable-date revision remains. At b72f03d8e196, no migration repeats. Stop on any other unexpected revision or multiple
heads. Do not run `alembic stamp` to mask a mismatch.

## Approved rollout and postflight

1. Deploy only the Warehouse API feature commit. The staging entrypoint validates
   configuration, obtains the existing PostgreSQL advisory lock, calls Alembic
   upgrade head, and only then binds its port. Do not run a separate racing
   pre-deploy migration or bypass startup with a direct uvicorn command.
2. Expected target: b72f03d8e196. This makes vehicles.acquisition_date nullable,
   preserving known dates and all rows without backfill. See QUICK_VEHICLES.md.
   The preceding checklist revision adds an empty, account-isolated
   vehicle_checklist_items table and nullable vehicle sync markers; no backfill.
   The preceding K-Type migration adds nullable vehicles.ktype plus a
   positive-value CHECK, no default/backfill. Existing donor rows remain unchanged
   with NULL; stock and operations are untouched. PostgreSQL DDL takes a lock:
   use a quiet staging window and inspect failures instead of increasing timeouts
   or restarting repeatedly. Migration errors prevent the new API from serving.
3. In the NEW API container at /app run read-only checks:

```sh
python -m alembic current
python -m alembic heads
python -m alembic check
```

Both revisions must be b72f03d8e196; check must find no schema drift.
4. Check the startup log contains "Warehouse migrations complete" and no
   migration/permission errors. Query API /health through the web origin after
   the matching frontend rollout. It compares DB revisions with packaged heads,
   not merely database connectivity:

```sh
curl --fail --show-error --silent https://YOUR-WAREHOUSE-WEB-DOMAIN/health
```

Expected: HTTP 200, {"status":"ok"}. No key or login is required for health.
The Nginx endpoint traverses API and DB. Do not treat static frontend rendering
or a successful build as proof of a healthy migration.
5. For a fresh installation create your real owner in the Warehouse API shell
   using `python -m app.create_owner` (interactive, no inventory seed, no password
   in command arguments). With provider disabled, verify login, manual vehicle creation, old donor
visibility, old stock/audit values and no automatic Plan.Parts network requests.
Only after explicit live-test approval enable the provider variables, make one
deliberate brand/model/modification workflow, verify the K-Type persisted, and
confirm no stock records were created. Only after licensed storage/reuse and paid
request approval, explicitly load a checklist in the donor card; verify new items
are unchecked and stock is unchanged. Reopening the card must make no provider request.

## Recovery decisions — Warehouse staging only

For a truly first deployment there is no previous healthy Warehouse release to
roll back to. On failure keep provider access disabled, stop only the failed
Warehouse application deployments if needed, retain the independent DB volume
and inspect revision/logs before retrying a corrected build. Do not delete the
database or attempt to use production as a fallback.

- **Migration failed transactionally:** do not deploy the new frontend. Read the
  DB revision and logs, verify the previous healthy API remains available, and
  fix the specific cause. PostgreSQL transactional DDL should leave the old
  revision, but inspect it; never assume. Retrying the corrected startup is
  supported and does not overwrite donors.
- **Migration succeeded, API bug:** disable Plan.Parts, prefer a forward fix
  retaining b72f03d8e196 and its checklist/K-Type/unknown-date data. An old API image alone is NOT a
  complete rollback: old /health expects f482ab1376c0 and rejects the newer head.
- **Full rollback approved:** stop Warehouse writes, preserve a new backup plus
  every non-null K-Type and all checklist items, translations and checks; select
  matching old API/web commits. Use the NEW API
  image's migration files (old image has no c91e72b6a410 revision) to downgrade:

```sh
python -m alembic downgrade f482ab1376c0
```

  The nullable-date downgrade refuses to proceed while unknown dates exist;
  never fabricate dates to bypass it. Earlier downgrades DROP the checklist
  table, sync markers and ktype, losing their values; execute only after separate approval.
  Then roll back only Warehouse API/web to the recorded commits, verify matching
  heads, /health, donor/stock counts and audit. Never downgrade base or edit audit.
- **Restore needed:** restore the verified snapshot to an isolated replacement
  Warehouse DB first, validate all data/revisions, then arrange an explicitly
  approved Warehouse-only switch. Snapshot restoration loses writes after the
  snapshot; reconcile them before opening the app. Never overwrite production.

Keep the provider disabled during recovery. Do not log keys, raw auth headers or
complete provider bodies while diagnosing failures.
