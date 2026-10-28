# Catalogue Import — draft and asynchronous review UX fix

Local change after `069d5182c3163d660d3e50b429faf9b1da647855`, branch `feature/carpot-warehouse-mvp`. No push, deployment or staging preview/apply was performed. No migrations, deduplication, planner, pricing, stock or finance logic changed.

## Confirmed staging state

The user supplied an authorized GET result for job `3b8eb380-e731-4f62-8545-c0336e015d7d` during this task:

- `status=ready`, `operation.kind=preview`, `operation.status=done`, `operation.error=null`;
- all six manual decisions are present in `resolutions`;
- `report.unresolved_total=0`, `report.skipped_rows=252`, `report.committed=false`;
- prospective inserts: 10 222 offers, 14 324 applications, 29 922 paths.

These are user-verified staging facts, not a GET executed from Codex. No Railway connector or authorized staging credentials were available here. The catalogue has not been applied according to that response. The six names themselves were not supplied to Codex; no claim is made that their content was inspected. The browser regression reproduces this state with synthetic data, without using the actual ZIP.

## Cause and state separation

The previous `accept()` copied `job.resolutions` into editable state and cleared `dirty` for every response. HTTP 202 acknowledges only queue acceptance and still contains the previous job/report/resolutions. The same destructive reset happened after request errors. This could erase the local six-name draft and display the old `review` report while a newer operation was running.

The new state model separates:

1. `draft`: current user input;
2. `pending.sent`: an immutable snapshot sent to a particular operation, with previous/current operation IDs;
3. `checked`: actual resolutions loaded from the server after completion.

A 202 never promotes old resolutions to the current draft. Polling continues through queued/running to the matching terminal operation, including when the acknowledgement itself already says done: a fresh GET still supplies the report. Completed preview must contain the submitted decisions; mismatched or concurrent operations block apply and retain local edits. Unknown acceptance after a timeout is reconciled using GET, never by automatically re-posting. If no new operation can be established, the old completed preview stays invalid and the user may explicitly retry.

Out-of-order selection requests are ignored, including a restore request that finishes after another upload or submission. Later edits never get overwritten by a terminal response. Confirmation is bound to the current preview token and resets when state changes.

## Draft storage and recovery

Drafts are automatically stored in **sessionStorage for the current browser tab** and survive page reload. The storage scope and serialized envelope include the authenticated actor/workspace identity, job ID and actual file SHA-256. No unscoped previous-user selection is restored. Payload shape/size are bounded and checked before restoration; mismatched drafts are rejected. Storage failures warn that fields remain in memory and the page should not be refreshed. The explicit Save draft button confirms local tab storage, not backend validation.

Opening an existing ready job without a browser draft uses its real server `resolutions`, including all six decisions in the reported staging case. Original source labels are preserved in new drafts. Older completed jobs do not retain all previous issue labels in the API report: where unavailable, the table explicitly says that the original name is absent and shows the actual saved decision, instead of inventing a source label or running another preview.

A minimal owner-only response extension exposes `operation.submitted_resolutions` for detailed preview operations. This allows recovery of accepted input during a running/failed operation if browser storage is absent. It is not proof of completed validation. Job history omits this payload, and session hashes are never exposed. Existing server owner allowlist/session/CSRF dependencies remain unchanged.

## User flow

1. Open/upload a file. Only required mappings appear in a compact editable table: source name, Ukrainian name or existing target, action and status.
2. Fill decisions. The draft counter shows e.g. “Підтверджено 4 із 6”, explicitly labelled as a draft until a new server preview validates it. Names persist through API errors and reload.
3. Click **Перевірити рішення**. Inputs are frozen during the operation, submitted values remain visible, and old report counts are hidden. Polling and errors show the actual current operation.
4. A matching ready preview shows the fresh report and “Перевірено сервером” statuses. New-entry recommendations (including a 9 542 count) are separate and optional; reviewing every entry is not required. Reference price comparisons remain available in the fresh report.
5. Only a valid current ready preview exposes the explicit confirmation checkbox. **Застосувати імпорт** appears after that checkbox is selected. Editing, pending/error state, a stale token or mismatched decisions disables eligibility again. No apply is automatic.

The table becomes labelled stacked rows on iPhone; screenshots passed an overflow check at 390px.

## Validation

- New pure state tests: **24 passed**. Covers stale-202 payloads, immutable sent snapshot, edits concurrent with completion, terminal report checking, polling/timeout recovery, errors, duplicate/different operations, out-of-order jobs, reload, actor/job/SHA envelope checks, clearing an input, and ready-job restoration without browser storage.
- Existing frontend unit suites: **215 passed** (team 53, smart search 65, workshop 97). Total frontend unit scenarios: **239**.
- Backend queue/access/serialization tests: **14 passed**. Confirms detailed submitted decisions, old job resolutions unchanged while queued, history payload omission, no session hash disclosure, fail-closed owner authorization and existing queue safeguards.
- TypeScript + Vite build: passed.
- Browser fault tests at **1440px and 390px**: six edits, 4-of-6 progress, old-resolution 202, polling, reload during operation, temporary GET 503, accepted POST 504, precise operation error, retained names, explicit retry, stale-ready apply protection and six-decision legacy ready-job restore without a new POST. **No apply** in these fault scenarios.
- Separate real LOCAL PostgreSQL/API browser flow at **1440px and 390px**: synthetic upload, preview, reload, explicit merge, explicitly confirmed local test apply and shared reading. Non-owner DIRECTOR sees denied UI and gets HTTP 403. This used only the isolated `warehouse_catalogue_v2_browser_test` DB; it is not a staging import.
- `git diff --check`: passed. All changes are under `warehouse/`.

## Reproduce

```bash
cd warehouse/frontend
node tests/catalogue-review-unit.mjs
node tests/team-unit.mjs
node tests/smart-search-unit.mjs
node tests/workshop-gate-unit.mjs
npm run build
# Local API + production assets only; scripts reject non-loopback origins:
WAREHOUSE_E2E=1 CATALOGUE_TEST_ORIGIN=http://127.0.0.1:18770 CATALOGUE_TEST_EMAIL=LOCAL_OWNER CATALOGUE_TEST_PASSWORD=LOCAL_TEST_PASSWORD node tests/catalogue-review-browser.mjs
```

Backend tests use a disposable PostgreSQL `warehouse*_test` database, never staging:

```bash
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_catalogue_v2_suite_test python -m pytest tests/test_catalogue_jobs.py tests/test_catalogue_v2.py::test_closed_by_default_and_actor_role_not_workspace_or_catalog_permission tests/test_catalogue_release_audit.py::test_all_admin_routes_closed_and_client_ids_cannot_impersonate -q
```
