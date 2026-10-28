# Final local release audit — 2026-10-28

Scope: branch `feature/carpot-warehouse-mvp`, original backend `036fee4b83839051e0a2d52da88cb76089d2934c`, UI/docs `fef1a0841ea46b5b5ca9deaccbc4c66d1d650286`, published base `9589e5e7bf4b7c694c885ddbdab62f18ea079715`. Worktree and previously uncommitted audit corrections survived environment restoration. All changes remain under `warehouse/`.

## Findings and corrections

- Explicit `create_name` of the same normalized label could re-enter its own resolution. Verified literal creation now bypasses that resolution, while retaining parent/type validation and rejecting ambiguous names. Exact-label and uppercase-label regressions cover preview, apply and repeat.
- Added an offline Aleto parser/prepared CSV converter with strict schema/relationship validation and no Warehouse DB access. `source_record` preserves all original fields verbatim, including whitespace and custom columns. An explicit Pydantic string constraint prevents inherited whitespace trimming of provenance.
- Unknown Aleto categories/subcategories require review. Original taxonomy remains the path identity, avoiding duplication against the existing v1 adapter.
- Root ZIP entry checks additionally reject Windows drive-style names, control characters and excessive names; empty upload basenames are rejected. ZIP contents are never extracted to arbitrary paths.

## Release gates

- Access: server allowlist defaults closed. All administration routes require an authenticated active allowlisted root DIRECTOR actor. Another workspace DIRECTOR, `catalog.import`, client account/actor IDs do not confer global rights. Other users can read shared reference data, not private stock or administrative jobs.
- Migration: sole head `021e8f6f220c`, directly after `b8716962f6b8`. Additive nine-table migration; no migration changes required by these fixes. Local populated-DB roundtrip/check is covered by regression tests.
- Data: no startup import/backfill, no workspace duplication of global catalogue. Legacy v1 readers remain; import tests fingerprint original tables including stock, reservations, sales, orders, personal prices, finance and audit.
- Import: CSRF, upload/expansion/ratio limits, persistent PostgreSQL jobs, payload SHA/token/revision validation, repeated apply, concurrent jobs, immutable price observations, idempotency and crash rollback/retry are covered by focused backend tests.

## Real-file limits

Real A is available and tested: 7 246 offers / 10 112 model links / 14 400 taxonomy paths. Prepared CSV conversion is canonically identical to the bundled v1 adapter for all 14 400 rows. Synthetic fixtures cover conversion and incremental changes.

Real B (10 222 offers) is unavailable. Its format, complete conversion, preview and expected deltas remain unverified. The reference deltas 2 976 offers / 4 212 links / 58 prices / 114 paths are not importer results. Use [CONVERSION.md](CONVERSION.md); reject unknown schemas rather than guessing mappings.

## Reproduction

Use a disposable local PostgreSQL database only:

```bash
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_catalogue_v2_suite_test python -m pytest tests/test_catalogue_release_audit.py tests/test_catalogue_v2.py -q
python -m alembic heads
cd ../frontend
npm run build
node tests/team-unit.mjs
node tests/smart-search-unit.mjs
node tests/workshop-gate-unit.mjs
```

No push, deployment, staging apply, production operation, Railway variable change or merge was performed. Staging runtime configuration/revision must still be checked at release time; this audit does not claim access to staging. Owner actor `bf89801e-2732-4605-9a4b-f65748cf4bf2` is configured via the server allowlist at release time, not hardcoded by this patch.

## Confirmed validation results

- Focused backend audit + v2 transaction/security/migration suite: **35 passed** (122.57s), one dependency deprecation warning.
- Frontend unit suites: **187 passed** (team 48, smart search 56, workshop gate 83).
- Production frontend build: passed (TypeScript and Vite).
- Alembic heads: exactly `021e8f6f220c`; regression includes downgrade to `b8716962f6b8`, upgrade and `alembic check` on populated disposable local DB.
- `git diff --check`: passed.

Code release readiness is separate from real-B import validation. Missing B blocks verification of its schema and reference deltas, not publication of the tested code to isolated staging. Before an actual B apply, obtain B, validate conversion and preview, and reconcile the report. No real-B result is claimed.

- Legacy Aleto v1 compatibility suite: **28 passed** (10.25s), including Volvo API and preservation regressions. Total backend checks in this resumed audit: **63 passed**.

**READY FOR STAGING RELEASE** — tested code only; real-B validation and staging runtime checks remain required before its import. Push requires separate authorization.
