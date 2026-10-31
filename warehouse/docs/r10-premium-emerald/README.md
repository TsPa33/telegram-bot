# CarPot Warehouse — R10 Premium Graphite & Emerald UI

Design direction approved by the user based on a visual concept. This implementation changes **only** Warehouse frontend presentation, preserves old routes and permissions.

## Appearance

- Graphite sidebar: `#111d1f`, text `#d7e4df`.
- Deep emerald primary: `#075544`, pressed `#033d32`, subtle surface `#e8f3ee`.
- Content surface: white; background `#f5f8f7`; text `#162825`; secondary `#62716d`.
- Danger, caution and success are separate semantic roles. A green CTA is not a success notification.
- Readable focus styles, accessible mobile tap targets, reduced-motion support.

## Scope

- `frontend/src/tokens.css`: single semantic palette that updates buttons, controls, badges and charts in all Warehouse routes.
- `frontend/src/premium-emerald-r10.css`: navigation, sidebar, headers, cards, inventory, catalogue, upload and multi-step status styling.
- `frontend/src/main.tsx`: globally load R10 stylesheet.
- `frontend/src/App.tsx`: concise administration navigation labels.
- `frontend/src/ParserAdminCenter.tsx`: real read-only KPI values, no sample mockup values; header polish.
- `frontend/src/pages/CatalogueImport.tsx`: visible icons on four existing functional catalogue sections.
- `frontend/src/DismantlingCatalogImport.tsx`: three-step status and **indeterminate** feedback while the existing API performs work.

## Data integrity

**No database schema changes, migrations, runtime flags or backend source changes.** Nothing changes stock, sales, money, audit, uploaded file history, source rights, parser credentials, pricing or catalogue imports.

The polished proof-of-concept mockup included example amounts and imagined layout elements. This release **does not insert those amounts or any synthetic rows**. Real catalogue KPI cards bind only to the existing `/catalogue/admin/overview` response. The local catalogue importer reads actual user-provided JSON and uses the existing dry-run/confirm operation.

The import progress indicator never claims a fabricated percentage. It shows a busy, indeterminate state until the endpoint responds.

## Checks

GitHub Actions run `41152916447`:
- `npm ci` success
- TypeScript and Vite production build success
- Frontend unit checks including theme contrast **460 passed, 0 failed**

No browser screenshots/7-viewport test on real staging were captured as part of this change. User acceptance should cover catalogue admin, vehicles/virtual inventory, inventory, sales, mobile navigation, animations, readability in 375 and 390 px, and errors/loading paths. Correct visual or navigation defects with a separate follow-up.

## Deployment

Merge only into `feature/carpot-warehouse-mvp`; never `main`. Railway staging's Web service should autodeploy from `/warehouse`. The API/Worker should be unchanged / skipped on Web-only code changes. Verify actual deploy status instead of assuming auto-deploy succeeded.
