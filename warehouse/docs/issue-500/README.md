# Issue #500 — physical split visibility / PR #499 audit

11.11.2026, Europe/Kyiv. Base: exact PR #499 head `4ddc21984e2ba98e629245a8478cb085d728cda1`, branch `feature/warehouse-pr5-physical-split-to-sale`. Focused follow-up branch `fix/warehouse-500-split-visibility`; PR #499/source branch/main/shared staging branch remain unchanged.

## What is proved, and what is not

**Local source defect reproduced on unmodified PR499:** `assemblyUnitFor({name:'Бампер (передній)'})` and the rear variant return null. The JS helper accepts only anchored `Бампер` (plus end-of-name «у/в зборі» normalization). The backend `family_for` also lacks these aliases. The JSX still wraps the entire split disclosure in `!!assemblyUnitFor(selected)`. Therefore these names hide the action even with DIRECTOR permissions, assembly flag on, stocked root, preview200, qty1 or qty6. The public issue calls the row «Бампер (передній)»; it does **not** prove the actual raw staging name.

**Second source defect:** all split markup sits inside the successful-preview branch (`!preview ? ... : ...`) and below photo/condition/note/stock controls. A slow/failed preview removes it completely; below-fold location can make a recognized root hard to discover in a scrolling inspector. Existing qty1/permissions/backend safety rules should disable the form, not remove the entry.

**Critical limit on the staging conclusion:** the issue also describes a quantity warning, «Фактичний склад» and physical management controls. In `4ddc219`, the warning itself uses `assemblyUnitFor(selected)` and those controls require a completed preview. If these exact elements are from that exact bundle, recognition/preview have already passed, so the alias defect alone **cannot explain that screenshot**. The disclosure should exist in the DOM; old/cached assets, different bundle, inspector scroll or actual field values need direct inspection. We do not label a guessed cause as the verified staging root cause.

The reported Web `4ddc219` / API `d372a9d` SHAs come from issue500/PR499 owner comments, **not a fresh Railway query**. Their diff changes only frontend `AssemblyTree.tsx`, CSS and its unit tests; that split UI version difference alone is not proof of API incompatibility. Live assets/ETag/cache/subpath/DOM/actor/assemblyEnabled cannot be verified here: one request to the canonical staging Web returned **CONNECT tunnel failed403, HTTP000**. No authenticated browser connector/session is available. An asynchronous request for an authorized channel was sent; no credentials were requested or used. No repeated Railway attempts/proxies. **Actual staging audit and authenticated staging E2E remain BLOCKED/UNVERIFIED.**

## Guard matrix checked in PR499

| Condition | Baseline behavior / evidence | Fix |
|---|---|---|
| Assembly name / alias | `assemblyUnitCatalog.ts:65`; backend family aliases; unknown returns null → no disclosure | Exact front/rear bumper aliases on BOTH sides; no substring component matching |
| Preview availability | Entire split UI inside `!preview` success branch | Disclosure above preview/photo; loading/error reason, no submit until preview succeeds |
| Inventory quantity6 | Existing recognized root displays a blocker, not six identified units | Same server qty1 invariant; clearer read-only unit-reconciliation steps |
| part_id, parent, consumed, archived, included, absent | `splitBlockReason` plus backend `_is_valid_root` | No relaxation |
| assemblyEnabled, editable, inventory.create | JSX formerly removed UI; latest PR499 explains blockers | Entry remains visible for recognized roots; write restrictions retained |
| reservations / stale token | preview conflicts + backend graph lock / no_reserves / composition token | No relaxation |
| Scroll / viewport | Disclosure below other inspector controls; native details internal scroll | Entry immediately after inspector heading; tested1440/390, keyboard-native disclosure retained |

The frontend map remains a generic REFERENCE, not installed components, VIN fitment or factory BOM. No quantity-derived membership, automatic cost allocation, or new receipt ledger.

## Minimal patch

- `assemblyUnitCatalog.ts`: anchored aliases for «Бампер (передній)/(задній)», suffix/prefix forms, normalized whitespace. «Облицювання бампера», «Підсилювач бампера», ambiguous/unknown descriptions stay unrecognized. Other families are not broadly reclassified.
- `backend/app/data/assembly_units_v1.json`: same exact bumper aliases for server validation. No migration or schema/index change, no rename of saved Parts.
- `AssemblyTree.tsx`: move the existing guarded split entry immediately after inspector heading and outside preview success rendering; explicit loading/error reason; qty6 read-only guidance. No changes to stock/split algorithms, permissions, service flags, prices, sales or reserves.
- Qty6 explains: physically identify one real unit; controlled allocation must preserve total6, leave5 in the lot and preserve reservations. **This screen does not implement lot-unit extraction.** Do not manually lower quantity or fabricate six new stock records. Split remains blocked until a genuinely reconciled qty1 root exists.

## Isolated verification

Two fresh databases were created in the existing **localhost-only test PostgreSQL** container: `warehouse_issue500_regression_test` and `warehouse_issue500_browser_test`, port55441. No existing test DB was reused/truncated for this issue. `conftest.py` migrations/TRUNCATE ran only against the dedicated regression DB. No Railway PostgreSQL/source MySQL connections or writes.

- **55 backend PASS**, full `tests/test_assemblies.py` + `tests/test_assembly_split.py`: atomic split/rollback, replay, concurrent reserves/sales, prior sold stock, original Part IDs, incomplete remainder + separate sale, cross-donor/permission/CSRF, 5 positioned bumper aliases, qty6 rejected without Part/Operation/membership changes, negative component-name matching. [Log](evidence/issue500-backend.txt).
- **251 frontend PASS + TypeScript/Vite production build PASS**, `npm run build` including prebuild suite. Existing bundle-size warning only. Before build was249 tests on exact base. [After](evidence/issue500-after-build.txt), [before](evidence/issue500-before-build.txt).
- **Authenticated local browser E2E PASS**, real app/auth/SQL/Part/Operation, no mocked inventory/source adapters. Fixtures are explicitly synthetic test stock, not staging/donor evidence. DIRECTOR role, actual permission list/readiness responses recorded; exact `/vehicles?donor=<owned-id>` route. Cases rear bumper1/front bumper6 plus door/engine1, both1440 and390.
- Before patch: both decorated bumpers lack the disclosure; door/engine controls exist. After patch: qty1 form selection/condition is visible, confirm button disabled until explicit checkbox; qty6 visible blocker/no component form. Read-only diagnostic Part/tree snapshots match before/after, POST count0.
- After that read-only diagnostic, a **separate explicitly opted-in LOCAL** confirmation in the same QA-only account executes the real split API from the UI: two distinct qty1 components, original root Part remains qty1/incomplete, original Part IDs preserved, front lot remains6. No duplicate receipt or sale inferred from templates. Backend suite separately verifies replay/rollback and actual sales.
- Injected local preview503 fault verifies the action is still visible/guarded, without data mutation. This fault injection is separately recorded, never represented as live service behavior.
- No unhandled JS errors or unexpected application-console errors in normal cases. Chromium additionally requests absent `/favicon.ico` from the preview host: pre-existing static HTML has no favicon, 404 is retained in the report (not claimed as zero console messages). The injected503 console entry is also retained. No new unrelated application/API error was hidden.

[Before report](evidence/before-local.json), [after report](evidence/after-local.json), [browser log](evidence/issue500-after-browser.txt). Local before asset `/assets/index-D6BMNoq_.js`, after `/assets/index-DBORSRAF.js` reflect our local builds, **not independently identified staging bundle hashes**.

### Screenshots — all LOCAL QA, not staging

| Case | Before | After |
|---|---|---|
| Qty1 desktop1440 | [before](screenshots/before-qty1-1440.png) | [after](screenshots/after-qty1-1440.png) |
| Qty1 mobile390 | — | [after](screenshots/after-qty1-390.png) |
| Qty6 desktop1440 | — | [after](screenshots/after-qty6-1440.png) |
| Qty6 mobile390 | [before](screenshots/before-qty6-390.png) | [after](screenshots/after-qty6-390.png) |

[Explicit local confirmation result](screenshots/local-confirmed-split.png).

## Reproduction commands

Backend (only a freshly isolated local *_test PostgreSQL; NEVER staging because conftest truncates):

```sh
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL='<dedicated localhost *_test URL>' python -m pytest -q tests/test_assemblies.py tests/test_assembly_split.py
cd ../frontend
npm run build
```

Local browser harness `backend/tests/issue500_browser_server.py` requires WAREHOUSE_E2E=1, WAREHOUSE_ENV=local and exactly localhost:55441/warehouse_issue500_browser_test. It refuses any other target. It uses the real application and only seeds a newly authenticated @example.test QA workspace. App must run on8040, Vite preview on5240 with WAREHOUSE_API_PROXY=http://127.0.0.1:8040.

```sh
WAREHOUSE_E2E=1 ISSUE500_PHASE=after ISSUE500_CONFIRM_LOCAL_SPLIT=1 node tests/issue500-browser.mjs
```

For an **authorized operator** on the actual canonical staging host, run the same browser check in fail-closed read-only mode (no seed/login/POST, all browser mutations/foreign origins blocked). Supply an existing browser storage file locally; do not commit/send credentials. Use a verified owned database UUID, not the display donor number. Requires existing qty1/qty6 bumper rows; does not create missing cases. Set WAREHOUSE_CHROMIUM_PATH if /usr/bin/chromium differs.

```sh
ISSUE500_TARGET=staging ISSUE500_PHASE=after \
ISSUE500_STORAGE_STATE=/private/authorized-browser-state.json \
ISSUE500_VEHICLE_ID='<owned-donor-UUID>' \
ISSUE500_OUTPUT=/private/issue500-staging-evidence \
node tests/issue500-browser.mjs
```

**The staging command has NOT been successfully run in this session.** Passing local runs must not be used as its substitute. Live mode rejects local confirmation and cannot execute split/sale/receipt. Staging logs should record actual source bundle/cache/permissions/readiness; compare to deployed SHA via authorized Railway before assigning an exact production-like root cause.

## Draft PR and deployment acceptance

Follow-up Draft PR base: `feature/warehouse-pr5-physical-split-to-sale` (PR499 head), head `fix/warehouse-500-split-visibility`. No push to PR499/shared staging/main; no merge. API and Web both need this fix because server family validation also changes. Review first; only then target existing warehouse-staging services. No worker/Variables/DB changes or manual migrations.

Before any staging deployment: confirm project/environment/service IDs, actual API/Web source SHAs and DB isolation through authorized Railway; ensure no source branch advanced unexpectedly. This issue has no migration changes. After deployment, verify API/Web same reviewed SHA, `/health`, startup logs, actual asset hash (hard refresh/new browser context), owned donor1/6 role/flag/DOM at1440/390 in **read-only diagnostic mode**. Any physical split/sale acceptance must be on separately authorized disposable QA data, never the real donor bumpers.

**Status: LOCAL SOURCE FIX / ISOLATED REGRESSIONS VERIFIED; REAL STAGING ROOT CAUSE + AUTHENTICATED STAGING E2E UNVERIFIED/BLOCKED.** Full issue500 acceptance is not claimed complete. Qty6 controlled lot-unit extraction remains intentionally unavailable; no financial cost allocation is implied.
