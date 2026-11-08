# Unified Catalogue — Volvo-first integration

**Current first-import corrections:** [FIRST_IMPORT_READINESS.md](FIRST_IMPORT_READINESS.md).
The initial review/upload procedure below is historical and superseded by that report.

Status: LOCAL IMPLEMENTATION / REAL DATA AND STAGING ACCEPTANCE BLOCKED.
Photos do not block catalogue development or dismantling. No image import is claimed.

## Provenance and limited audit

Integration branch: `integration/volvo-unified-catalogue`, based on Warehouse
`cc41f7e3cf13a4b61ee5d5c74ef20626089f6d3c`. Catalogue module copied intact from
`origin/feature/carpot-catalogue-mvp` at `50be491efa4e3ab48413a965fd119d7ff2d0a994`,
then extended. The subsequent remote documentation update
`c34966ceea6734dcad21192d974754199bbfe258` was incorporated before commit. Other branch/root/Telegram code was not merged or rewritten.
Read: VOLVO_DEEP_AUDIT_FACTS, UNIFIED_CATALOGUE_PLAN, VOLVO_PILOT,
Warehouse PLAN_PARTS and DISMANTLING. The latter two describe historical initial
implementations; current saved receipts, persistence and workspace code were also inspected.

Source facts (user's Windows audit, NOT independently queried here): Volvo120,
XC90II13084/9 variants, XC60II37773/6 variants, exact car107555 T6AWD,
107556 D5AWD with duplicate textual labels, 126478 XC60D4AWD.
`passanger_*` spelling is preserved. Article applicability is joined using exact
car `linkageid` + `linkagetypeid=2`, product ID, supplier ID and article number.
No source ID is written into Vehicle.ktype.
The earlier 499,841 OEM scan is not asserted as Railway's current unique count.
`GET /api/v1/volvo/diagnostics` or `volvo_target.py` provides the actual target count.

No Windows source, Railway CLI/connector/token, Catalogue endpoint credentials,
or MySQL credentials are available in this execution session. Real import count
for this work: **0**. Target existing counts, deployed SHAs, isolation/bindings and
actual Alembic revision: **UNVERIFIED**. No Railway Variables/configuration changed.

## Implemented

- `catalogue/volvo_vehicle_import.py`: local SELECT-only Volvo passenger source,
  exact models/modifications, raw specs/tree/PDS/QSI, product/article links,
  suppliers, OEM, crosses, attributes, image metadata. Defaults to the two verified
  model IDs, never global links or other makes. Link reads keyset-paginated250.
- Per-variant atomic file checkpoints with SHA-256, completed-file resume,
  single-process output lock, caps100 variants/run,20,000 rows/identity,8MiB
  per variant and estimated3,500MiB target guard. An interrupted variant is
  re-read; completed variants are reused. No assertion of per-page resumability.
  Missing tables/columns or caps fail instead of publishing truncated data.
- Snapshots are initially **partial**, even after source traversal completes.
  Explicit offline review (`volvo_review.py`) is required for Ukrainian names,
  3-level taxonomy, source links and completeness. No invented translations.
- Additive MySQL tables in `catalogue/volvo_integration.sql`:
  `catalogue_volvo_snapshots`, `catalogue_suppliers`, `catalogue_volvo_versions`. No source/Warehouse DDL,
  backfill, stock or financial table modifications; not executed remotely.
- Existing `/api/v1/volvo/article` reviewed: parameterized exact supplier+number
  SQL; number comparisons now binary, OEM still manufacturer120, cross-only.
  Verified supplier names/observation time become available after selective import.
  Legacy lookup remains compatible before new supplier table exists.
- Key-protected modification/coverage/categories/articles/plan/diagnostics APIs.
  Snapshot checksum and exact identity are checked before serving.
- Server-only `CatalogueAdapter`: HTTPS exact configured host, no redirects,
  bounded body/deadline, no browser key, errors fall back without secrets.
- `CatalogueResolver`: verified full exact Catalogue -> saved Plan.Parts ->
  existing explicitly confirmed paid UI (optional) -> free standard CarPot.
  Resolver itself never issues paid requests. Partial/outage cannot masquerade
  as verified coverage. No K-Type inferred from names, OEM or source IDs.
- Source-independent read-only `/unified-catalogue/enrichment` works for a Part
  from any plan; requires an existing article/brand and exact verified supplier
  identity. It returns cross-reference evidence, never automatic field writes.
- Catalogue plans use existing `Vehicle.dismantling_v3` JSON and
  `DismantlingItem`; no duplicate plan/stock model and no PostgreSQL migration.
  Compact source projection retains labels, source IDs, observation time,
  taxonomy status and a pinned SHA; raw detail is stored centrally by version. Existing annotations/translations remain authoritative.
- Existing `DismantlingBoard` reused for corporate categories, filtering,
  Ukrainian/original names, annotations, stock UI and settings. Same donor page;
  no parallel application or navigation section. Existing Plan.Parts flow retained.
- No stock at plan creation. Only explicit confirmed receipt uses the existing
  stock ledger and row locks; retry/concurrent receipt cannot add another unit.
  Article/OEM lists never multiply physical positions. Vehicle identity changes preserve the plan but require review before stock/number writes.
  Existing donors with
  plans/stock are protected by409 rather than guessed cross-source merging.
- Saved article assignment validates donor/workspace/exact plan row/physical Part,
  server offer ID and optimistic current article fields. Manual article protected.
  OEM cross assignment is separate, explicit and never overwrites an existing OEM.
  Provenance records source article/supplier/time/checksum/user and VIN=false.
  Search/stock card updates use existing inventory-changed event and Part fields.

The Catalogue-first flow currently exposes the two verified model families.
Expansion requires source audits and reviewed taxonomy mappings. It is not a
claim that all makes or all Volvo generations are ready. Existing-plan merging,
20 real article acceptance samples and real source SQL performance remain gates.

## Images

Three independent sources: existing user donor/Part photos (priority), future
verified licensed catalogue assets, existing labeled CarPot placeholders.
`article_images.PictureName` stays metadata only; no generated URLs, hotlinks or
fabricated actual photos. User reports `2_E325.JPG` absent under C:\CarPot;
`2_M892.JPG` existence and all redistribution rights are unverified. Parts and
OEM remain usable without them. No external image is fetched by this integration.

## Windows commands / first import

Use the current [first-import procedure](FIRST_IMPORT_READINESS.md), including
zero-connection preflight, explicit107555 allowlist, independently verified SHA
and expected partial coverage. The old combined taxonomy/completeness flag is
removed. Do not run an old all-file upload command or treat translation as proof
of full vehicle coverage.

## Staging activation / rollback

1. Verify both staging environments/databases/bindings independently. No production.
2. Apply only the explicitly reviewed MySQL DDL above; it is NOT wired to startup.
3. Run selective export/review/upload, inspect actual diagnostic counts, compare
   all source IDs for XC90II and at least20 exact article/OEM cases plus negatives.
4. Configure server-only WAREHOUSE_CATALOGUE_URL (actual HTTPS origin),
   WAREHOUSE_CATALOGUE_HOST (that exact hostname), WAREHOUSE_CATALOGUE_KEY
   matching Catalogue's CATALOGUE_API_KEY. No VITE variables or MySQL access in UI.
   These settings have NOT been added in this session.
5. Deploy Catalogue with its root `/catalogue`/Dockerfile; deploy Warehouse
   API/Web from the integration commit only after branch/source review. No worker
   changes needed. Warehouse packaged Alembic remains sole head `e641b3a20f97`.
6. Synthetic local test is not staging acceptance. In authorized staging workspace
   create XC90II, explicitly choose exact source modification, save, verify
   categorization/articles/OEM/manual edits, explicitly receipt one test detail,
   retry, reopen, verify no paid calls. Test partial/outage and XC40 fallback.
7. Read-only health/logs/deployed SHAs/revisions and browser1440/390 must pass
   before calling the real integration complete.

Rollback: retain DB tables and frozen saved plans. Disable access to new Catalogue
selection while preserving existing rows; no DROP, TRUNCATE or downgrade. Old
Warehouse code can coexist with the unchanged PostgreSQL schema, but cannot render
new Catalogue plans; forward fix/new UI preferred. Do not delete source or stock.

## Local verification

Dedicated PostgreSQL: localhost55440 / `warehouse_volvo_integration_test` only.
Fixture tests migrate/truncate that isolated DB. No source/staging/production writes.

- Backend targeted tests: unified Catalogue, existing checklist and free category recovery.
- Catalogue contract/API/source-query tests: mocked source/MySQL cursor, no real SQL claim.
- Frontend targeted units, TypeScript+Vite build, Chromium1440/390 against guarded
  local API and PostgreSQL. Screenshots `/tmp/carpot-unified-catalogue-browser/`.
- Browser harness forces synthetic Catalogue and Plan.Parts transports; its
  source data must never be imported into a real catalogue or represented as real Volvo.
- Build has the existing >500kB chunk advisory; TestClient has a deprecation warning.

Verified results: 23 unified integration tests + 13 existing checklist/recovery
regressions = 36 PASS (targeted runs); 6 Catalogue contract/query/schema tests PASS; 31 targeted
frontend units PASS; TypeScript/Vite build PASS. Chromium at1440/390 verifies
save/reopen, explicit one-unit receipt, article assignment and separate OEM cross
assignment, no external/paid requests, no JS errors and no horizontal overflow.
Screenshots in `screenshots/` contain synthetic data only. MySQL DDL and source
queries have NOT been executed against the real Windows/Railway databases.
The actual commit hash is in the task report (no self-referential hash in this file). No commercial
source-license assumption follows from the presence of local database records.
