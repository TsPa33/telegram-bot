# CarPot Checkpoint №057 — OEM auto-assignment diagnostics

Date: 2026-11-19.

## Scope
Warehouse staging only. No paid VIN/OEM API, no donor/part update and no changes to OEM references or production.

## Confirmed code findings
1. OEM already exists in source code in `warehouse/backend/app/services/auto_oem.py`. A background worker sweeps active donor vehicles about every 120 seconds, if Catalogue credentials exist. Platform admin must not expose import/load OEM buttons to users.
2. Exact auto-assignment deliberately requires (a) confirmed source catalogue modification + reviewed part type with available article/OEM; OR (b) exact supplier brand + article number. Mere OEM presence in local MySQL does NOT establish compatibility with a specific VIN or stock part.
3. Known reviewed pilot: Volvo XC90 2016 VIN `YV4A22PK2G1092943` may match modification `107555`. The code does not infer DAF XF 2007 or Volvo XC60 2022 modification from VIN alone because they have no verified engine code or pinned catalogue snapshot in the user's API results.
4. Found a defect: `source_identity` and `SourceCache.resolve_directory` compared `year` with integers without guarding for `None`. This could throw and abort a sweep for donor records with unknown production year.
5. Railway staging has `WAREHOUSE_CATALOGUE_URL`, `WAREHOUSE_CATALOGUE_HOST`, `WAREHOUSE_CATALOGUE_KEY` (variable names only). Runtime logs show Catalogue API HTTP 200 for modification 107555 and product IDs 188/288, so Catalogue network access is possible. This does **not** prove that a specific OEM was assigned.
6. The existing local MySQL / Railway Catalogue data has not been exhaustively counted live in this stage. Do not claim comprehensive coverage.

## Implemented
- Guard incomplete year in automatic OEM matching, fail safe without throwing.
- Read-only audit API: `GET /api/v1/oem/admin/coverage`, authenticated, platform-admin-only, `vehicles.view` permission; no provider/network requests, no changes, no secrets, aggregate counts for three control VINs (vehicles, included dismantling rows, references, parts with OEM/articles, reasons for missing mapping).
- New tests in `test_oem_diagnostics.py`, route allowlist, CI.
- No new consumer-facing OEM button or notification.

## Next
1. CI PASS; staging-only deploy.
2. Read admin-only coverage for DAF, XC90 and XC60 (must be same authorized browser session).
3. For each missing link determine whether reason is missing modification, type match, supplier article, OEM source or absent stock rows.
4. Only exact, auditable cross-references may auto-populate; preserve manual overrides.
5. Once stage #057 audit is verified, implement the specific failure fixes; still no paid OEM lookup.

## Evidence
GitHub PR, commit SHA, CI and Railway deploy IDs should be recorded only after returned by tools.
