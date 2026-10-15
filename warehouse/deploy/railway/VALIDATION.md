# Railway staging preparation — local validation

No Railway account, deployment, service, volume, domain, production database, or CarPot credentials were accessed. All checks below ran locally in a disposable Compose project, separate from the pre-existing Warehouse development stack. Nothing was merged or pushed.

## Results

| Check | Result |
|---|---|
| Production backend Docker build | Passed, Python 3.11 image, hashed dependency install, readable immutable source, non-root runtime |
| Production frontend Docker build | Passed, TypeScript/Vite build stage, Nginx-only runtime (no Vite server) |
| Backend suite in staging image on PostgreSQL | **26 passed**, no skipped tests; one Starlette test-client deprecation warning |
| Staging database component URL handling | Passed, reserved password characters round-trip safely |
| Migration rerun, competing startup lock, rollback/release on failure | Passed |
| Readiness requires current Alembic head | Passed |
| Real local HTTPS smoke | Passed with hostname-verified local CA; no global TLS bypass |
| Host/origin/CSRF and secure cookies | Passed; closed public registration; cookie paths preserved through proxy |
| Production assets, direct SPA paths, API 401/404 preservation | Passed |
| Production browser workflow: desktop 1440×1000 | Passed: login, secure cookies, deep links, CSP, responsive rendering, logout |
| Production browser workflow: iPhone viewport 390×844 | Passed: same checks, responsive cards and no page overflow |
| API replacement / DB-session continuity | Passed: migrations rerun, existing record and session survive replacement |
| Backend unavailable | Frontend `/health` correctly fails instead of claiming readiness |
| Volume-bootstrap privilege drop | API PID 1 runs uid 1000 after root-owned photo mount preparation |
| Local service manifest, source/watch paths, shell syntax, Compose config | Passed |
| TypeScript/Vite build outside Docker | Passed |
| Ruff undefined/unused-name checks | Passed |
| Existing tracked files outside `warehouse/` | Unchanged |

The final complete `WAREHOUSE_CHROMIUM_PATH=/usr/bin/chromium python deploy/railway/check-run.py` run exited 0. Its disposable database contained test fixtures only and was removed at the end. Temporary TLS keys and plaintext test login data were deleted; ignored responsive screenshots remain in `.check/`. The check does not seed any real staging environment.

A local packaging issue was found and fixed: workspace files with mode 0600 needed explicit read permissions inside non-root images. Early checks also exposed two test-harness issues (an invalid registration payload and attempting to parse an empty 204 as JSON); those were corrected, and the final complete run passed. Assertions and application validation were not disabled.

## Files added for this task

- `warehouse/.dockerignore`: deployment build context excludes local secrets and generated outputs.
- `warehouse/RAILWAY_STAGING.md`: exact project/service/variable/volume/domain and feature-branch instructions, iteration and rollback constraints.
- `warehouse/deploy/railway/backend.Dockerfile`, `frontend.Dockerfile`: dedicated production images.
- `warehouse/deploy/railway/frontend-start.sh`, `nginx/nginx.conf`, `nginx/server.conf.template`: non-root production static serving, private runtime DNS, canonical HTTPS proxy, host/security headers.
- `warehouse/deploy/railway/services.json`, `staging.env.example`: reviewable Dashboard settings, variable references and secret requirements; no credentials or automatic Railway apply.
- `warehouse/deploy/railway/check-config.py`, `check-run.py`, `check-browser.mjs`, `check-edge.conf`, `compose.check.yml`: local-only configuration, PostgreSQL, HTTPS/browser and restart verification.
- `warehouse/deploy/railway/VALIDATION.md`: this report.
- `warehouse/backend/app/staging.py`: guarded startup, serialized transactional migrations, privilege drop and dual-stack Uvicorn.
- `warehouse/backend/app/create_owner.py`: explicit interactive creation of a real owner; no startup account seeding.
- `warehouse/backend/tests/test_staging.py`: seven meaningful staging/migration tests, in addition to the existing nineteen.

## Files updated

- `warehouse/backend/app/config.py`: Railway DB components, canonical public origin, staging and registration options.
- `warehouse/backend/app/main.py`: staging origin/host protection and migration-aware readiness.
- `warehouse/backend/app/api/routes.py`: registration option endpoint and closed-registration enforcement.
- `warehouse/backend/alembic/env.py`: support a caller-held migration-lock connection while keeping normal Alembic CLI behavior.
- `warehouse/frontend/src/pages/Auth.tsx`: reflect disabled registration without a broken signup action.
- `warehouse/scripts/build-cloud-images.py`: optional local proxy/CA builder now supports the staging image pair.
- `warehouse/.gitignore`: ignore local staging-test certificates, credentials and screenshots.
- `warehouse/README.md`, `warehouse/API.md`: link staging deployment instructions and describe staging auth behavior.

The existing development Dockerfiles, development Compose configuration, shared/root dependency declarations, and every CarPot application/startup/deployment file remain unchanged by this task.

## Remaining external steps

Commit/push `feature/carpot-warehouse-mvp`, then follow `RAILWAY_STAGING.md` when you choose to deploy. Railway-specific settings admission, GitHub access, actual private addresses, persistent-volume provisioning, generated domain/TLS issuance and physical iPhone Safari remain unverified because actual deployment was explicitly out of scope. There is no live preview URL yet. Expected format: `https://<warehouse-web-generated-domain>.up.railway.app`.
