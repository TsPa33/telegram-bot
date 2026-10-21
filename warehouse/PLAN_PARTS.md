# Plan.Parts vehicle selection — Warehouse only

Staging preflight, migration-state checks and rollback procedure:
[PLAN_PARTS_STAGING.md](PLAN_PARTS_STAGING.md). The user-provided real exports in
backend/tests/fixtures are replayed offline; no paid provider requests are made.

## Implemented

The backend uses httpx and the confirmed Playground GET contracts:

- `https://cdn.plan.parts/api/v1/aftermarket/catalog/brands`
- `/v1/aftermarket/catalog/models?mfa_id=...`
- `/v1/aftermarket/catalog/modifications?ms_id=...`

Warehouse exposes authenticated, CSRF-protected POST actions:

- `/api/v1/plan-parts/brands/lookup`
- `/api/v1/plan-parts/models/lookup?mfa_id=121`
- `/api/v1/plan-parts/modifications/lookup?ms_id=1994&year=2001`

The optional Warehouse `year` filter is local; it is NEVER sent as an invented
provider parameter. Results include every compatible modification, not an
arbitrarily chosen K-Type. The frontend fetches modifications once per explicit
load and filters years locally, so changing year does not cause paid requests.

The vehicle dialog offers searchable brand/model/modification selects, a year
input, explicit load/retry buttons, errors/loading, power, displacement and
production periods. Parent changes clear dependent selections. No provider calls
run on page load or opening the dialog. Manual vehicle creation remains available.
Vehicle POST/PUT persists nullable `ktype`; manual edits of identifying fields
clear a previous K-Type instead of silently retaining a stale match.

## Railway variables — Warehouse API service only

- `PLAN_PARTS_ENABLED=true`: opt in to potentially paid calls; default false.
- `PLAN_PARTS_API_KEY`: set through private Railway Variables; never frontend/Git.
- `PLAN_PARTS_MODEL_NAME_FIELD`: optional override; defaults to `name`, confirmed
  by the real Volkswagen export. Leave unset or use `name`. An invalid override
  fails closed rather than hiding a missing model name.

Existing PORT, database, secure-cookie, public-origin and frontend proxy settings
remain unchanged. No frontend API key or VITE variable is needed.

## Required database change — NOT applied to any working database

`backend/alembic/versions/c91e72b6a410_vehicle_ktype.py` adds nullable vehicles.ktype
and a positive-value CHECK after revision f482ab1376c0. It leaves existing rows
and audit history intact. No database backfill or inventory creation is included.
The updated ORM requires this column: do not run the new application against an
unmigrated database. Review and authorize the staging migration before deploying.
The existing `python -m app.staging` entrypoint applies migrations under its DB
advisory lock. No Railway resources/configuration were changed by this task.

## Costs, isolation and security

No permanent/global response cache, background synchronization, automatic retries
or bulk loading is implemented. Provider results exist only in request/browser
memory; selected vehicle fields are ordinary account-owned Warehouse records.
The shared backend key is never sent to the browser. Provider bodies/credentials
are excluded from returned errors. Redirects are disabled and TLS verification
stays enabled. Responses are limited to 2 MiB decoded data and 10,000 records.
Connect timeout: 5 seconds; read/write/pool timeout: 10 seconds each, not a total
deadline. Unknown JSON structures fail closed.

Attempt limits per API process: identical account+lookup+selector once per
60 seconds, up to 10 attempts/account/minute and 60 attempts/minute overall.
Failures count, parallel identical lookups are suppressed, and different users
never share cached results. A 429 response provides Retry-After: 60. The frontend
does not retry automatically. State resets on process restart: this is NOT a
provider token/spend cap. Use one API worker/replica; provider spending caps and a
distributed limiter are needed before scaling. Token prices/balance API are unknown.

## Verified exported contract and remaining license review

The ZIP supplied by the user contains four exports copied without alteration to
backend/tests/fixtures. The observed shape is:

```json
{"success": true, "data": {"count": 0, "results": []}}
```

Observed records: 708 brands, 292 models (data.mfa_id=121), 35 modifications
(data.ms_id=1994, data.limit=100), 632 category types (data.ktype=9743).
The parser validates success, count consistency, selectors, positive integer IDs,
duplicates and known numeric/date fields. It rejects partial/truncated responses;
it never follows pagination or performs extra billable requests automatically.
Legacy bare arrays remain supported for backward compatibility.

Model name is `name`; periods are `year_from`/`year_to` in YYYY-MM. The model export
contains 76 null end dates, preserved as null. GOLF IV (1J1), ms_id=1994, is 1997-08
through 2008-04. K-Type 16063 is 1.9 TDI, 1896 cc, 96 kW / 130 PS, 2000-11 through
2005-06. The backend normalizes dates to years for inclusive year filtering and
the frontend shows model periods. Supported legacy formats additionally include
integer YYYY, string YYYY and ISO YYYY-MM-DD. Unknown starts are excluded when
filtering; unknown ends do not impose an upper bound, and the UI labels them
"end not provided" rather than asserting that manufacture continues today.
A null value's presence is confirmed; its complete business semantics are not
established by an export alone.

The categories export is validated offline against pt_id/name/article_count only;
there is still NO categories fetch route, import or stock creation. article_count
is never treated as quantity. catalog_url is not followed. Licensed reuse,
translations and persistent production caching remain unverified. The test files
are user-provided fixtures, not a seeded production/global catalogue. Do not enable
live use until rights and a separately approved paid-test budget are confirmed.

## Offline checks

From warehouse/backend with installed dependencies:

```sh
PYTHONPATH=. python -m pytest unit_tests -q
```

These tests use MockTransport and fake auth DB dependencies, not PostgreSQL.
The existing `tests/` suite must run ONLY on a dedicated warehouse*_test PostgreSQL
because its fixtures migrate and truncate that database.

From warehouse/frontend:

```sh
npm run build
node tests/plan-parts.mjs
```

The browser test starts a loopback Vite preview of production assets and intercepts
all backend responses. It uses Chromium at desktop/iPhone-sized viewports, not
physical Safari, and never contacts Plan.Parts. Chromium defaults to /usr/bin/chromium;
set WAREHOUSE_CHROMIUM_PATH if needed. No deployment is performed.
