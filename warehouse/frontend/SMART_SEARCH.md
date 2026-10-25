# UX 5.7 Stage 3 — Smart Search frontend

Local implementation only, isolated at `/workspace/carpot-ux57-stage3` from
`e5ca4e1ea488e7e9155a4e3345b5c901d87759c9`. No commit, push, deployment, Railway
change or staging DB operation is authorized by this preparation. The published
backend's actual Railway deployment/migration has not been independently verified.

## Integration and compatibility

The existing SalesWorkspace quick-search screen adds “Звичайний пошук” and
“Розумний пошук”, with standard search selected initially. Both modes reuse the
same result cards, Part detail, sale/request_key handling, price editor, notes,
Orders and history. Standard search still calls `/api/v1/parts`; Smart mode calls
`/api/v1/smart-search/parts`. No search response creates or rewrites inventory.
Smart mode uses available quantity after reservations; standard mode preserves
its existing physical-stock filtering semantics. “Показати без залишку” enables
zero-stock inspection in Smart mode, with unavailable sales still disabled.

Stage 1 WorkshopGate is unchanged, including its strict single known head and
four Workshop features. The UX 5.6.1 donor metadata grouping, layout CSS and
container-based narrow-panel cards are retained unchanged. No backend, schema,
API wire contract, migration, stock ledger, sale idempotency or pending-request
code is modified. The old local WorkshopDialogs diff is deliberately NOT copied.

## Independent readiness

Only the quick-search page probes `GET /api/v1/smart-search/readiness`.
Smart mode is enabled only after:

- HTTP **200**, not any generic successful status;
- `status=ready`, numeric `contract_version=8`;
- `required_revision=a73e05b9c842`;
- `database_revisions=["a73e05b9c842"]` exactly: no missing, duplicate, unknown
  or mixed heads;
- all `tenant_ranked_parts`, `direction_constraints`, `dictionary_aliases`,
  `bounded_typo_search` features (additional features are allowed).

`smartSearch.ts` is the pure validator. `api.ts` adds an optional expected HTTP
status argument used only by this readiness call; all existing callers keep
their previous status handling, credentials and error/401 behavior. A missing,
malformed, pending or failed readiness cannot trigger a Smart parts request.
The page explains temporary unavailability and offers a retry. Standard search
and Workshop v7 do not depend on Smart Search readiness. A 401 still invokes
the existing session logout behavior; it is not bypassed to preserve a search UI.

## Search behavior

One input, 300ms debounce, existing donor/brand/model filters and server limit 50
with offset pagination. Filters remain selected across modes; mode changes reset
the page. Search key includes mode and effective parameters. Existing useLoad
cleanup ignores stale responses, and display guards suppress old results while
query/mode is changing, loading or failing. Loading, network errors, 503 retry,
empty results and clarification are explicit. An ambiguous query shows the
server clarification, without a random result or confidence percentage.

Results show actual donor, price/currency, available quantity and server match
explanation. Clearing the query uses the same input. Existing keyboard suggestion
navigation, pointer/touch selection and Part dialogs are reused. Search state
is local to the mounted workspace, not a new persistent index or stock cache.

## Local checks

The browser harness uses disposable PostgreSQL 16 with Stage 2 migrations and
real controlled Part records. Error/readiness cases intercept only those
responses. No real Plan.Parts or paid AI requests are used. “Real records” in
these tests means local test inventory, not production/staging customer records.

Required cases cover `мозги мотора XC60`, left/right rear lights,
`передня ліва дверка`, `radik volvo`, `капотт`, exact OEM/article, ambiguity,
unknown query, zero stock, delayed stale response, network failure, 503,
standard/Smart switching, strict readiness rejection and 401 session handling.
53 real test Parts validate server pagination, non-overlapping stable pages and
donor filter preservation. A double click on priced sale sends one mutation;
the last unit becomes zero and stays visible only with “show zero” enabled.

Screenshots are ignored test artifacts in `test-results/smart-search-1440.png`,
`smart-search-768.png`, `smart-search-390.png`, not proposed release files.
Browser viewports: desktop 1440x1000, tablet 768x1024, iPhone 390x844. Physical
Safari is untested. All current regression entrypoints are run; workflow.mjs is
a helper exercised by browser-check.mjs. Deferred UX 5.5 catalog-scene-browser
is not part of the published baseline and is not copied or run.

## Remaining deployment limits

The new frontend is guarded, but a future release still needs explicit approval
and authenticated live v8 verification after the Stage 2 backend Auto Deploy.
Do not assume GitHub publication proves a migration or deployment succeeded.
Backend 100k broad-query timeout limits documented in SMART_SEARCH_STAGE2.md
remain; this frontend surfaces 503 and does not fabricate fallback matches.
There is no external AI, automatic fitment inference, new search algorithm,
new migration or background inventory ingestion in this stage.

## Final local results

**READY for review**, not a claim of successful Railway deployment.

- Production TypeScript/Vite build passed.
- **42 unit tests passed** (22 existing image/resolver tests + 20 Smart tests).
- **All 17 existing baseline browser suites passed**, plus the expanded Smart
  Search browser suite: **18 suites total**. The strengthened stale-response
  test waits for the late response to actually return before checking results.
- Smart Search covers all three requested viewports; the UX 5.6.1 regression
  additionally checks CSS zoom 125% and 150%. Physical browser UI zoom and
  physical Safari have not been tested.
- Readiness rejects HTTP 404/503, network failure, invalid status, numeric
  contract mismatch, wrong required revision, missing/empty/unknown/mixed/duplicate
  heads, each missing feature and even HTTP 201 with a valid JSON body.
  No Smart search request is sent in those cases. HTTP 401 preserves logout.
- Real local API results, server pagination, priced last-unit sale with double
  click, missing-result/ambiguity, 503 retry, stale result suppression, keyboard,
  donor filter retention, zero stock and standard fallback passed.
- git diff --check passed; backend, WorkshopGate and UX 5.6.1 CSS unchanged.
- Original worktree contents, UX 5.5 untracked files and full local UX 5.7 are
  preserved; final verification compares path sets and SHA-256 hashes.

Proposed frontend-only files:

- `warehouse/frontend/src/SalesWorkspace.tsx`
- `warehouse/frontend/src/api.ts`
- `warehouse/frontend/src/smartSearch.ts`
- `warehouse/frontend/src/smart-search.css`
- `warehouse/frontend/tests/smart-search-browser.mjs`
- `warehouse/frontend/tests/smart-search-unit.mjs`
- `warehouse/frontend/SMART_SEARCH.md`

No dependency/package, global CSS, WorkshopDialogs, backend or migration change.
No screenshots/test-results are proposed release files.

