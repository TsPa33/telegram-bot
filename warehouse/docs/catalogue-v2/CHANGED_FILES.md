# Змінені файли Universal Catalogue v2

База `9589e5e7bf4b7c694c885ddbdab62f18ea079715`. Усі 45 файли лише під `warehouse/`; gitignored screenshots/build outputs до комітів не входять.

- `backend/alembic/versions/021e8f6f220c_global_catalogue_v2.py`
- `backend/app/api/catalogue.py`
- `backend/app/api/catalogue_limits.py`
- `backend/app/api/deps.py`
- `backend/app/api/routes.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/catalogue.py`
- `backend/app/permissions.py`
- `backend/app/route_registry.py`
- `backend/app/services/catalogue_format.py`
- `backend/app/services/catalogue_import.py`
- `backend/app/services/vehicle_catalog.py`
- `backend/tests/conftest.py`
- `backend/tests/test_catalogue_v2.py`
- `backend/tests/test_dismantling_readiness.py`
- `backend/tests/test_dismantling_v2.py`
- `backend/tests/test_plan_parts_migration.py`
- `backend/tests/test_quick_vehicle.py`
- `backend/tests/test_smart_migration_permissions.py`
- `backend/tests/test_staging.py`
- `docs/catalogue-v2/CHANGED_FILES.md`
- `docs/catalogue-v2/FORMAT.md`
- `docs/catalogue-v2/README.md`
- `docs/catalogue-v2/REPORT.md`
- `docs/catalogue-v2/validation.json`
- `examples/catalogue-v2/README.md`
- `examples/catalogue-v2/bmw-audi.csv`
- `examples/catalogue-v2/bmw-audi.zip`
- `examples/catalogue-v2/manifest.example.json`
- `examples/catalogue-v2/volvo-increment.csv`
- `examples/catalogue-v2/volvo-initial.csv`
- `frontend/src/App.tsx`
- `frontend/src/GlobalCatalogue.tsx`
- `frontend/src/WorkshopDialogs.tsx`
- `frontend/src/access.ts`
- `frontend/src/pages/Catalog.tsx`
- `frontend/src/pages/CatalogueImport.tsx`
- `frontend/src/smartSearch.ts`
- `frontend/src/teamReadiness.ts`
- `frontend/tests/catalogue-v2.mjs`
- `frontend/tests/smart-search-unit.mjs`
- `frontend/tests/team-unit.mjs`
- `frontend/tests/workshop-gate-browser.mjs`
- `frontend/tests/workshop-gate-unit.mjs`

## Окремий локальний release-audit commit

- `backend/app/api/catalogue.py`
- `backend/app/services/catalogue_format.py`
- `backend/app/services/catalogue_import.py`
- `backend/app/services/catalogue_convert.py` (новий)
- `backend/tests/test_catalogue_release_audit.py` (новий)
- `docs/catalogue-v2/FORMAT.md`
- `docs/catalogue-v2/CONVERSION.md` (новий)
- `docs/catalogue-v2/FINAL_RELEASE_AUDIT.md` (новий)
- `docs/catalogue-v2/CHANGED_FILES.md`

## Local timeout fix after `760d5e2`

Runtime: `backend/app/services/catalogue_import.py`, new `catalogue_jobs.py`, `backend/app/api/catalogue.py`, `backend/app/main.py`, `backend/app/models/catalogue.py`. Additive migration: `backend/alembic/versions/41f9a2c87d10_catalogue_operations.py`. Reproducible local performance script: `backend/scripts/benchmark_catalogue_jobs.py`.

UI: `frontend/src/pages/CatalogueImport.tsx`; new-head compatibility in `teamReadiness.ts`, `smartSearch.ts`, `WorkshopDialogs.tsx`. Tests: new `backend/tests/test_catalogue_jobs.py`, updated catalogue helpers, six existing readiness/migration head expectations, backend fixture worker isolation, and frontend browser/readiness tests. Docs: README, CHANGED_FILES, TIMEOUT_FIX, timeout-benchmarks.json. All remain under Warehouse.

## Local review UX fix after `069d518`

- `frontend/src/pages/CatalogueImport.tsx`, `frontend/src/catalogueReview.ts`, `frontend/src/catalogue-import.css`, `frontend/src/App.tsx`
- `frontend/tests/catalogue-review-unit.mjs`, `frontend/tests/catalogue-review-browser.mjs`, `frontend/tests/catalogue-v2.mjs`
- `backend/app/api/catalogue.py`, `backend/app/services/catalogue_jobs.py`, `backend/tests/test_catalogue_jobs.py` (owner-only read-only submitted-decision metadata)
- `docs/catalogue-v2/REVIEW_UX_FIX.md`, README, CHANGED_FILES

No schema/planner/deduplication/stock/price/finance changes.
