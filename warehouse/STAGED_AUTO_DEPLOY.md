# GitHub-only, backend-first Warehouse Auto Deploy

Auto Deploy stays ON. No Railway CLI, manual deployment, new services, production
changes or Plan.Parts calls. Use the EXISTING warehouse-staging and postgres.
This document prepares publication only: no commits/pushes/deployments have run.

## Dashboard prerequisites — before publishing anything

Select only warehouse-staging in the existing Railway project. Check the EXISTING
backend and web services have source TsPa33/telegram-bot, feature/carpot-warehouse-mvp,
Root Directory /warehouse, one replica, and Auto Deploy ON. Do not rename/recreate
an existing backend whose actual label differs from warehouse-api. Preserve its
working private origin (e.g. telegram-bot.railway.internal:8010), HTTPS domain,
cookies, proxy, ports, DB credentials, POSTGRES_* and volumes. Apply no production
settings. Source/settings changes can themselves schedule a Railway rollout:
review pending Dashboard changes in an approved window, not as a manual Deploy action.

Watch Paths are repository-relative even with Root Directory /warehouse. Set EACH
pattern separately, not a comma-separated string:

Backend:
```text
/warehouse/backend/**
/warehouse/deploy/railway/backend.Dockerfile
/warehouse/.dockerignore
```

Frontend:
```text
/warehouse/frontend/**
/warehouse/deploy/railway/frontend.Dockerfile
/warehouse/deploy/railway/frontend-start.sh
/warehouse/deploy/railway/nginx/**
/warehouse/.dockerignore
```

Do not use /warehouse/** on either service: it defeats the two-push separation.
Backend coverage includes app/data JSON, requirements.lock, schemas, routes and
Alembic files. Frontend coverage includes package/lock, src, index.html, tsconfig,
vite.config and both Nginx files/runtime script. Tests also trigger their respective
service; docs outside these directories do not. Root bot files are not build inputs.
The only shared build input here is .dockerignore: it must remain UNCHANGED in
this rollout; changing it triggers both. services.json/check scripts/docs do not
trigger either service, and are not consumed as Railway IaC. Committing the
manifest does NOT set Dashboard Watch Paths or Variables. Confirm settings first.

In the template, DB references now use postgres:
```text
WAREHOUSE_DB_HOST=${{postgres.RAILWAY_PRIVATE_DOMAIN}}
WAREHOUSE_DB_PORT=5432
WAREHOUSE_DB_NAME=${{postgres.POSTGRES_DB}}
WAREHOUSE_DB_USER=${{postgres.POSTGRES_USER}}
WAREHOUSE_DB_PASSWORD=${{postgres.POSTGRES_PASSWORD}}
```
These refer to existing values, not replacement credentials. Existing working DB
Variables need no change. Do not apply the template's example first-install
POSTGRES_DB/USER/PASSWORD/volume settings to the already initialized postgres.
No public TCP proxy; no changes to its data or schema before an approved rollout.
API startup remains python -m app.staging; both app healthchecks remain /health.

## Local pre-publication checks

From repository root:
```sh
python warehouse/deploy/railway/check-config.py
python warehouse/deploy/railway/check-watch-paths.py
git diff --check
git status --short
```
The watch checker derives Docker COPY inputs, including directory additions, and
proves backend files never match web patterns and vice versa. This is local
validation, not proof of Dashboard settings or Railway's live GitHub integration.
Backend tests require a dedicated LOCAL warehouse*_test database; frontend uses
npm run build and existing browser tests. No paid API calls.

## Phase A — backend publication, only after separate commit/push approval

Keep ALL warehouse/frontend changes unstaged/uncommitted while publishing A.
Stage these paths only (from repository root); review staged paths and secrets:
```sh
git add -- warehouse/backend warehouse/deploy/railway/services.json warehouse/deploy/railway/check-config.py warehouse/deploy/railway/check-watch-paths.py warehouse/STAGED_AUTO_DEPLOY.md warehouse/RAILWAY_STAGING.md warehouse/deploy/railway/VALIDATION.md warehouse/DISMANTLING.md warehouse/PLAN_PARTS_CHECKLIST.md warehouse/PLAN_PARTS_STAGING.md warehouse/QUICK_VEHICLES.md
git diff --cached --name-only
git diff --cached --check
```
Expected: backend implementation/tests/migration + local template/checks/docs,
NO frontend paths and NO shared .dockerignore. Then, only when authorized:
```sh
git commit -m "feat(warehouse): add dismantling API and staged rollout readiness"
git push origin feature/carpot-warehouse-mvp
```
Stop here. Do NOT commit/push B yet. On GitHub/Railway Dashboard verify the pushed
SHA starts only the existing Warehouse backend deployment; web must remain on
its previous SHA. Do not click Deploy/Redeploy. If web also starts, the live Watch
Paths are wrong: halt the second push and investigate; local template cannot stop it.

The automatic backend entrypoint applies additive d53c9a27f608 under its advisory
lock, then binds the private port. Verify the API deployment is healthy at A's SHA
and startup log says Warehouse migrations complete. No separate manual migration.
Old web continues using the old API contract against the new backend. Existing
endpoints and /health JSON stay compatible. Old API /health may briefly return
503 after the DB head changes during replacement: plan a short staging maintenance
window, not a guarantee of zero downtime. No destructive migration is involved.

## Mandatory gate before phase B — browser only, no supplier or stock writes

Log in through the EXISTING Warehouse web HTTPS domain. The old web already proxies
all /api/v1 paths, so in that same browser open:

1. https://YOUR-WAREHOUSE-WEB/health — 200.
2. https://YOUR-WAREHOUSE-WEB/api/v1/dismantling/readiness — 200, JSON:
```json
{
  "status": "ready",
  "feature": "dismantling",
  "contract_version": 1,
  "required_revision": "d53c9a27f608",
  "database_revisions": ["d53c9a27f608"],
  "catalog_source": "carpot.base.v1",
  "catalog_items": 33
}
```
3. https://YOUR-WAREHOUSE-WEB/api/v1/vehicles/EXISTING-DONOR-ID/dismantling — 200,
   items and counters. An empty list before Start is correct. Obtain ID from the
   authenticated /api/v1/vehicles list; do NOT create a replacement donor.

These GETs need only the existing HttpOnly session, perform no writes, add no
stock, and call no Plan.Parts. No keys/tokens/passwords in URLs, commands or logs.
401 means log in; 404 means old API/no route; 503 means schema not ready. Any of
these, an HTML SPA response, wrong contract/revision/catalog count or wrong backend
SHA blocks B. /health=200 alone is insufficient. If login/session is broken, stop
rather than relaxing CSRF/cookies. Live settings and checks must be verified by the
operator; this workspace has no authenticated Railway access.

## Phase B — frontend publication after A passed the gate

Only after A is healthy and every check above passes, review the remaining diff:
```sh
git add -- warehouse/frontend
git diff --cached --name-only
git diff --cached --check
git commit -m "feat(warehouse): add donor dismantling workspace"
git push origin feature/carpot-warehouse-mvp
```
The B push differs from A only under frontend/, so only web should Auto Deploy;
API remains at A (B contains A as its parent). Confirm Dashboard SHA and /health,
then readiness JSON and desktop/iPhone login/navigation. Real Start/receipt writes
on staging remain a separately approved test, not part of this publication gate.
Keep Plan.Parts disabled. Do not merge main.

Two commits pushed together are NOT two stages. Do not push B while A is building,
and do not include backend changes, .dockerignore or other shared triggers in B.
The authenticated readiness endpoint is an operator gate between pushes, not a
claim that arbitrary simultaneous Auto Deploy is now safe.

## Failure handling — GitHub-only

If A fails build/migration/readiness: do not publish B. Inspect logs and actual
revision, retain the verified pre-rollout backup, then propose a backend-only fix
commit/push after approval. Do not force a stamp/downgrade, reset DB or use production.
If B fails: keep healthy A; correct frontend in another frontend-only commit/push.
A frontend-only revert is compatible with A. Backend code rollback to a revision
that expects the old Alembic head can fail /health; prefer a forward fix. A failed
migration/backup restore requires separate explicit approval; no manual redeploy.

## Verified locally for this preparation

- 153 backend tests passed, including authenticated read-only readiness, 401 for
  anonymous access, 503 for old revision and 503 for a missing table even at head.
- GitHub HEAD's unchanged frontend production build was run against the new API
  and real dedicated local PostgreSQL: full inventory workflow passed on desktop
  and iPhone viewport. This verifies phase A does not require the new frontend.
- Docker COPY/watch coverage and cross-service exclusion checks passed; no root
  railway.json/toml overrides exist in this checkout.
- Frontend production build and both offline browser scenarios passed. New
  frontend + new API production-preview workflows also passed on real local
  PostgreSQL, desktop and iPhone viewport, including receipt, audit, idempotence,
  bulk operations and reload. Staging/Safari/live Dashboard settings are not tested
  by these local checks. Short API replacement downtime is still possible.
