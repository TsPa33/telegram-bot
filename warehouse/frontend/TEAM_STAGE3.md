# UX 5.8 Stage 3 — Team Management Frontend

## Release boundary

Base: `6371f75a8eaaf5953e67d9a4405f2d2a635dab9a` (published Stage 2).
Isolated worktree: `/workspace/carpot-ux58-stage3`.
Only frontend source, frontend tests and this document belong to Stage 3.
No backend, migrations, dependency manifests, Dockerfiles, Compose, Railway
Variables or UX 5.5 changes. Full `/workspace/carpot-ux58` remains preserved.
Stage 2 is confirmed live by the user, not independently verified by this frontend
work. Local commit preparation is authorized; no push/deployment is performed.

## Implemented interface and real contracts

- Settings -> Team uses GET /team/readiness, /team and /team/permissions.
  Contract v9 requires the sole head b94f62d18e07 and all five server features.
  Unknown/incomplete responses fail closed for Team without blocking Workshop.
- Director sees workspace accounts and can manage eligible employee roles,
  permissions, blocking/reactivation and password reset. Admin sees/manages
  managers only. Unknown roles never inherit director UI access.
- All 31 permission keys and Ukrainian labels come from the server registry;
  grouped explanations clarify their scope. No alternative permission system.
- Directory shows name/email, role, active/blocked/mandatory-password state,
  permission count, creation/last-login dates and actor-specific audit links.
  It requests 50 rows per page. Name/email, role and status filters explicitly
  apply **only to the current page**, because the API has no global team search.
- Forms use actual POST/PATCH/reset contracts. An admin cannot select ADMIN,
  add permissions outside grantable, reset a broader manager, or reactivate
  broader retained permissions. Server enforcement remains authoritative for
  stale forms and direct API requests.
- Temporary passwords stay in masked form state; they are not put in URLs,
  localStorage, notifications, logs or directory responses. Delivery is manual
  through a private channel; there is no email/invitation service.
- Mandatory password change shows the personal name/role/workspace and requires
  a new password before business screens. Reset and change revoke old sessions.
  Double submit is guarded. Blocking explains that sessions will end, while
  audit/history remain intact.
- Personal identity appears in the header, with a responsive identity line on
  mobile/tablet. Existing menu items/actions use server-reported permissions.
  The full advanced operations interface remains available to fully permitted
  users; granular actions remain on part cards. Audit-only users can open the
  journal without requesting inaccessible inventory/vehicle lookups.
- Optional lookups in sales/orders/history/vehicles/catalog respect their read
  permissions. No forbidden import/archive/edit/sale controls are presented as
  usable. Existing donor hierarchy and ordinary inventory/order mechanisms stay.
- Financially redacted fields display restricted/absent sections, never fake
  zeroes or invented historic sale amounts. Audit/order history uses real actor
  names/snapshots, or an explicit unknown marker for missing historical identity.

## Activation stays OFF

The frontend cannot enable employee creation. It reads the boolean
`employee_creation_enabled` from readiness. With false, Team still loads existing
accounts, a clear Ukrainian notice explains creation is temporarily disabled,
and creation is not offered. The backend independently rejects POST /team.

Do not set `WAREHOUSE_TEAM_CREATION_ENABLED=true` in Railway during Stage 3.
Only isolated local test processes temporarily set it true. No runtime frontend
request writes environment variables or substitutes a fake readiness result.

## Cache, session and request safety

- Access is checked from the personal identity, not workspace-owner assumptions.
  A security key includes actor, workspace, role, permissions and password-change
  state. Changing it remounts protected screens, discarding cached server rows,
  open dialogs and old in-flight loaders. Financial values already fetched before
  revocation are not reused after the updated identity is accepted.
- Identity is rechecked on protected API 403, focus/visibility return and every
  30 seconds while signed in. Listener/timer cleanup and request generations
  prevent late profile responses from restoring a logged-out/previous user.
  This is polling/event refresh, **not server-push real-time notifications**.
  Server authorization is immediate; an idle open tab may retain its previously
  authorized display until its next identity check (up to the polling interval).
- Authentication endpoints do not recursively emit permission-refresh events.
  A normal 403 with unchanged identity keeps the failed form/error visible;
  remounting blindly would retrigger mount-time requests such as donor prepare.
  If identity verification fails, protected content is hidden until retry/login.
- A changed browser CSRF/session during a protected request discards that old
  response and refreshes identity instead of rendering another account's data or
  logging out the newly signed-in user. Its result remains uncertain rather than
  being classified as a definitive mutation failure.
- Existing pending stock/order keys remain scoped to the individual actor in
  sessionStorage. They contain client-authored commands, not cached financial
  API responses, and are retained for safe recovery after navigation/reload.
  Do not erase unknown commands on logout/permission refresh or retry with a new
  key. An order replay denied with 403 retains the original key/body until the
  actor is authorized again; denial cannot prove the earlier request did not
  commit. A real integration test covers lost committed response -> revoke ->
  denied replay -> restore -> same-key replay, with exactly one order/no receipt.
- As with other same-origin applications, this does not protect sessionStorage
  from a person with browser developer-tool/OS access. Shared workstations should
  use separate browser profiles. No passwords or session tokens are persisted
  by the Team feature in web storage.

## Local test procedure

Use existing Warehouse images/dependencies and only the Compose profile test.
Supply WAREHOUSE_POSTGRES_PASSWORD privately in the local process environment.
Never point tests at Railway or development DB. db_test is tmpfs/private and has
no host PostgreSQL port. The existing tests service mounts current backend and
Warehouse scripts read-only; this avoids stale image code.

From repository root, initialize the disposable test schema:

```sh
docker compose -f warehouse/docker-compose.yml --profile test up -d --no-build --wait db_test
docker compose -f warehouse/docker-compose.yml --profile test run --rm --no-deps --entrypoint sh tests -c 'export WAREHOUSE_DATABASE_URL="$WAREHOUSE_TEST_DATABASE_URL"; exec python -m alembic upgrade head'
```

Run the real API in another terminal (only HTTP port is published):

```sh
docker compose -f warehouse/docker-compose.yml --profile test run --rm --no-deps -p 127.0.0.1:8010:8010 -e WAREHOUSE_ENV=development -e WAREHOUSE_COOKIE_SECURE=false -e WAREHOUSE_REGISTRATION_ENABLED=true -e PLAN_PARTS_ENABLED=false -e WAREHOUSE_TEAM_CREATION_ENABLED=false --entrypoint sh tests -c 'export WAREHOUSE_DATABASE_URL="$WAREHOUSE_TEST_DATABASE_URL"; exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8010'
```

Build frontend, serve its production assets on local 5173 with the existing Vite
preview proxy to 127.0.0.1:8010, then run tests from warehouse/frontend:

```sh
npm run build
node --test tests/*unit.mjs
WAREHOUSE_E2E=1 node tests/team-disabled-browser.mjs
```

For team-browser and team-security-browser only, restart **that local API** with
creation true. Never change Railway. The security suite accepts
WAREHOUSE_VIEWPORT_WIDTH=1440, 768 or 390. Restart between large batches to keep
normal process-local authentication limits intact; do not disable the limiter.
Stop local API/frontend before stopping db_test. PostgreSQL is never exposed.

Team/security acceptance uses real server authorization and actual PostgreSQL
records, not auth/readiness mocks. Its only network interception drops an already
committed response to test uncertainty/idempotency. The two existing Plan.Parts
provider UI suites use offline fixtures/mocked responses; their explicit director
profile was updated for the real role-shaped frontend contract. They do **not**
serve as evidence that Team backend authorization works. No paid provider calls.

Final local results:

- Production TypeScript/Vite build passed; all **152 frontend unit tests passed**.
- All **18 existing browser regression runners passed** (workflow.mjs is a helper,
  not an additional executable suite). This includes the two offline provider UI
  suites discussed above. No paid API was called.
- Three Team acceptance runners passed: team-browser, team-disabled-browser and
  team-security-browser, covering desktop 1440x1000, tablet 768x1024 and iPhone
  viewport 390x844 with real Stage 2 APIs/PostgreSQL. Total: **21 browser runners**.
- The last pending-request safety correction was additionally rechecked in the
  real security flow on all three viewports and the full orders-browser regression.
  The final compact permission layout was rechecked by team-browser on all three
  viewports, plus the disabled-creation and phone security flows.
- The disabled suite deliberately requires a real false flag. An invocation with
  the enabled test server was rejected by its assertion; the proper false-server
  rerun passed all three viewports. The assertion was retained, not skipped.
- Zero-right lookups do not generate 403/remount loops. Real CSRF rejection keeps
  an unchanged-identity form/error visible; actual permission changes invalidate
  cached financial snapshots. Admin reset/reactivation bounds, single reset,
  mandatory password change and real actor display passed.
- Pagination exercised 52 local workspace accounts, with limit=50/offset=50 and
  correct page-local filters. No staging employee was created.
- Frontend-only file boundary, preserved Stage 1 gates, git diff checks, local
  Railway Watch Paths checks and secret scan passed. Original UX 5.5 and full
  UX 5.8 statuses/file checksums match the preservation snapshots.
- No backend or migration changes; no backend test results are relabeled as new
  Stage 3 runs. No live Stage 3 deployment or physical Safari test was performed.

Screenshots are ignored local test artifacts, not release files:
`test-results/team-permissions-1440.png`, `team-stage3-security-390.png`,
`team-disabled-390.png` and tablet counterparts.


## Frontend-only rollout and Stage 4 handoff

Before a future approved push, recheck origin and Stage 2 live v9 readiness with
b94 head. Confirm employee_creation_enabled=false. Backend source remains the
published Stage 2 artifact. No migration is introduced by Stage 3.

Existing Watch Paths: `/warehouse/frontend/**`, frontend Dockerfile/start script,
Nginx directory and .dockerignore. This package changes only the first path.
Backend watches `/warehouse/backend/**`, backend Dockerfile and .dockerignore;
none changes here. Existing Dashboard paths must match; local check scripts are
not Railway IaC. Do not rename telegram-bot/confident-sparkle/postgres or create
new services. Only confident-sparkle should Auto Deploy after a separate approval.

After frontend Active, verify the exact artifact, login as an existing director,
Team directory/31 labels, disabled-creation notice/no creation action, stock,
orders, financial/audit presentation and Smart Search on desktop/iPhone. Verify
v5-v9 and false activation again. Do not create staging employees during Stage 3.
Stage 4 separately authorizes activation, private password handoff, real employee
activation/password change, granted/denied operations, block/reset/revoke/audit,
and physical iPhone Safari checks. No automatic Stage 4 or financial mutations.

## Exact proposed release files (30)

- `warehouse/frontend/TEAM_STAGE3.md`
- `warehouse/frontend/src/App.tsx`
- `warehouse/frontend/src/Dismantling.tsx`
- `warehouse/frontend/src/InventoryWorkspace.tsx`
- `warehouse/frontend/src/Orders.tsx`
- `warehouse/frontend/src/PowertrainEditor.tsx`
- `warehouse/frontend/src/SalesLedger.tsx`
- `warehouse/frontend/src/SalesWorkspace.tsx`
- `warehouse/frontend/src/StockHistory.tsx`
- `warehouse/frontend/src/Team.tsx`
- `warehouse/frontend/src/access.ts`
- `warehouse/frontend/src/api.ts`
- `warehouse/frontend/src/orderRequests.ts`
- `warehouse/frontend/src/pages/Audit.tsx`
- `warehouse/frontend/src/pages/Catalog.tsx`
- `warehouse/frontend/src/pages/Dashboard.tsx`
- `warehouse/frontend/src/pages/Inventory.tsx`
- `warehouse/frontend/src/pages/Settings.tsx`
- `warehouse/frontend/src/pages/Vehicles.tsx`
- `warehouse/frontend/src/permissions.tsx`
- `warehouse/frontend/src/shared.tsx`
- `warehouse/frontend/src/team.css`
- `warehouse/frontend/src/teamReadiness.ts`
- `warehouse/frontend/tests/plan-parts-checklist.mjs`
- `warehouse/frontend/tests/plan-parts.mjs`
- `warehouse/frontend/tests/team-browser.mjs`
- `warehouse/frontend/tests/team-disabled-browser.mjs`
- `warehouse/frontend/tests/team-security-browser.mjs`
- `warehouse/frontend/tests/team-unit.mjs`
- `warehouse/frontend/tests/vehicle-images-browser.mjs`
