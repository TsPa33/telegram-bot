# Stage 2C — activation, constructive functions and one dismantling workflow

Base: `3589a21041f4cb36b9e8a6b09ad7b0e7e7881680`. Local Warehouse-only change. No push, deployment, staging preview/publish/backfill, production action, variable change or bot startup was performed.

## Why 33 positions remained visible

The v2 offer import and canonical publication are separate operations. Importing 10,222 v2 offers does not set `CanonicalState.snapshot_sha`. `canonical_candidates.candidates()` returns `published:false` when that value is empty. `dismantling_preview.preview()` then uses the original **33-position base**. Deployment deliberately does not publish or update existing vehicle plans.

This causal path is reproduced against PostgreSQL with a real v2 import and read-only fingerprints. **The actual staging snapshot was not read in this session**; absence of publication there remains a diagnosis to confirm, not an asserted live observation. A stale rules fingerprint is a distinct condition: publication exists but requires a new owner preview/publication, rather than silently reinterpreting old mappings.

### Read-only diagnostics

Owner-only UI: `/administration/catalogue/import` → “Конструктивний каталог”. It shows v2 offers/paths/models, publication state, mapped offers/types/placements, unresolved counts, and an optional vehicle selector. SHA/rule versions/raw administrative details are collapsed and do not appear in the seller workflow.

Owner-only endpoint:

```text
GET /api/v1/catalogue/admin/canonical/diagnostics
GET /api/v1/catalogue/admin/canonical/diagnostics?vehicle_id=<own-workspace-vehicle-id>
```

It reports `published`, actual `snapshot_sha`, executable and published rule versions, `rules_current`, mapped offers, active snapshot types/placements, unprocessed/review records, per-vehicle candidate count and `fallback_used`. Stored historic reference totals are separate from current-snapshot totals. Optional vehicle lookup enforces the actor's workspace. The endpoint never enqueues, normalizes, publishes or saves anything.

For an authorized operator with existing Warehouse DB environment, the alternative CLI forces a PostgreSQL **READ ONLY** transaction:

```sh
cd warehouse/backend
python scripts/diagnose_canonical.py --vehicle-id <vehicle-id>
```

No credentials, connection strings or session tokens are printed. The ordinary managed-plan GET exposes only a simple publication/rules/fallback status and plan counts, not administrative SHA or raw mappings.

## Constructive catalogue

`app/data/canonical_universal_v2c.json` defines **216 shared constructive functions** spanning engine, fuel/exhaust, transmission/drive, body, cabin, electronics/lighting, chassis/brakes/steering, cooling/climate, safety and high voltage. Existing type IDs and original 33 source keys remain stable. **194 additional templates** complement the original 33 installation positions, giving **227 baseline potential positions after explicit publication**, independently of market listings.

These are reviewed engineering vocabulary/templates, not an OEM bill of materials or manufacturer fitment certification. Provenance states their scope and limitations. Existing identities are reused; Volvo/BMW/Audi do not get separate type definitions for the same function. New uploaded names match only complete exact Ukrainian phrases in their explicit context; there is no fuzzy matching or OEM-derived identity. Ambiguous names stay in review.

A constructive template has unknown side/position, no OEM and no inferred installed quantity. Petrol/diesel/HEV/PHEV/BEV, drive and options are conditional evidence. Missing options never mean absence. Unverified items remain “Потрібно перевірити”; a verified conflicting fact can mark a candidate incompatible without deleting it. A plan row's existing draft receipt quantity default does not establish installed quantity; preview quantities remain null and stock quantity requires a separate explicit receipt.

Rules and template content participate in `RULE_FINGERPRINT`. An existing publication from an older release requires owner re-preview and re-publication; no automatic reinterpretation or backfill occurs.

## Owner publication without SQL or API tokens

The existing durable PostgreSQL queue and endpoints remain authoritative:

1. Open global catalogue administration as an allowlisted platform owner. No re-upload of Volvo B is required.
2. Click **“Перевірити нормалізацію”**. POST `/canonical/runs` enqueues a preview; UI polls GET `/canonical/runs/{id}` through queued/running/done/error states. It restores the latest durable run after reload. Lost enqueue responses are reconciled through diagnostics; transient polling errors retain status and retry.
3. Read counts and inspect unresolved groups if needed. Unprocessed records can remain unresolved; there is no obligation to inspect every market listing.
4. “Переглянути неоднозначні групи” pages through exact-context groups. Select a known constructive type, supply technical evidence, preview the exhaustive group rule, then explicitly confirm it. The existing `/rules/preview` and `/rules/approve` endpoints preserve conflicts, source conditions and append-only revisions. This saves a rule, **not the catalogue**. If its revision changed, “Перевірити актуальне правило” re-previews the server-reported revision before another explicit confirmation. Versioned constructive templates are immutable inputs; market group aliases do not redefine them.
5. After changing rules, run normalization preview again. Only a completed normalization preview exposes **“Опублікувати каталог”**, gated by its own explicit checkbox.
6. Publication submits the server-issued preview ID/token internally. Changed source/rule snapshots are rejected; the UI displays the exact error and requires a new preview. Tokens and replay IDs are never copy/paste tasks.

Every server operation uses the existing allowlist, session identity, CSRF and worker-time reauthorization. Missing allowlist, another workspace's DIRECTOR, or `catalog.import` alone grants no publication rights. No new Railway variables or Redis service are required. The existing catalogue worker must remain enabled to process explicitly queued commands; startup never enqueues preview or publication.

## Vehicle workflow

One main **“Розбір автомобіля”** interface replaces parallel Aleto/managed/read-only screens. Previous catalogue/source tools remain collapsed under “Попередній довідник та джерела”; data and APIs remain compatible.

- Header: vehicle/model/year/VIN, short engine/transmission editing and collapsible configuration facts.
- Six indicators: total, unchecked, physically present, excluded, dismantled, **actual positive stock**. Received/sold history remains separate internally; 30 historical receipts need not mean 30 current stocks.
- Search, category/subcategory/status filters, collapsible groups, cards on phone and desktop. Rendering starts with 60 rows and expands in batches; selection applies to the explicitly labelled filtered set, capped at the server's 1,000-item command limit.
- “Оновити каталог” checks available candidates, existing matches and ambiguities without saving. Only explicit save creates/updates plan rows. Existing exclusions and historic rows are retained. Broad/refined positions that may describe one physical part require a one-to-one manual decision.
- Presence, absence, exclusion/restoration and dismantling remain distinct commands. Ordinary reversible actions do not require extra confirmation checkboxes. **“Додати на склад”** still requires explicit quantity/confirmation and existing inventory rights.
- Plan-save replay IDs, etags, source SHA and preview tokens remain internal. Lost-response retries retain request keys; repeat generation does not create duplicate plan rows or receipts. A failed recheck disables application of its old proposal.

No GET, normalization preview or publication creates a Part or receipt. Publication never mutates DismantlingItem, stock, selling prices, finance or user exclusions. A separate explicit plan update reuses exact legacy identities and preserves original IDs. Protected stock-history rows can only be changed through the existing stock workflow.

## Evidence and limitations

[Real A evidence](real-A-validation.json), real bundled 7,246-offer / 14,400-path Volvo A, three models:

| Measure | Result |
|---|---:|
| XC60 2018 candidates before publication | 33, fallback used |
| XC60 2018 candidates after publication | **341**, no fallback |
| Active canonical types | 216 |
| Global installation positions | 348 |
| Constructive/OEM variants from A | 1,444 |
| Recognized offers | 1,128 / 7,246 (15.57%) |
| Unprocessed records | 11,450 |
| Review records | 155 |

Offer recognition coverage has **not** increased beyond 1,128; the broader possible-parts list comes from explicit constructive functions. Records/paths and offers are different denominators. Unknown fitment remains unknown. **Real Volvo B was unavailable and was not tested**; no claim is made about its normalized candidate count or live staging snapshot.

The XC60 regression uses synthetic business history: 33 old rows, 30 actual receipt histories, one subsequently sold position and **29 current positive stocks**. It verifies all old IDs, status/exclusion/receipt links, every existing operation byte-for-byte, all Part rows including prices/costs, safe addition, repeat save, bulk exclusions/restoration and workspace separation. These are local fixtures, not copies of user records.

Screenshots use real local auth/API and production frontend, Chromium at 1440px/390px, not physical iPhone Safari:

- [Desktop overview](screenshots/stage2c-plan-1440.png) / [cards](screenshots/stage2c-cards-1440.png).
- [Phone overview](screenshots/stage2c-plan-390.png) / [cards](screenshots/stage2c-cards-390.png).
- [Unpublished warning](screenshots/stage2c-unpublished-1440.png).
- [Owner normalization preview](screenshots/stage2c-owner-preview-1440.png).

[Browser results](browser-results.json) distinguish the 227-position synthetic constructive fixture from real A. The owner group UI uses a clearly synthetic single source, not an asserted real Aleto equivalence.

## Reproduce locally

Use only disposable loopback databases ending `_test`. Pytest and fixture seeding erase their target. Never point these commands at staging.

```sh
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage2c_suite_test \
  python -m pytest -q

# Separate browser DB, already created and migrated to head:
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage2c_browser_test \
  python scripts/seed_stage2c_browser.py --confirm-disposable
```

The fixture writes `/tmp/stage2c-browser-fixture.json` with owner and donor IDs. Start a local API on 8016 with that owner ID in the local process allowlist, browser test DB as `WAREHOUSE_DATABASE_URL`, secure cookies disabled only for loopback and the catalogue worker enabled. Start Vite preview on 5186 with `WAREHOUSE_API_PROXY=http://127.0.0.1:8016` after `npm run build`. No Railway variables are changed.

```sh
cd warehouse/frontend
WAREHOUSE_E2E=1 node tests/stage2c-browser.mjs
WAREHOUSE_E2E=1 node tests/dismantling-preview-browser.mjs
WAREHOUSE_E2E=1 node tests/managed-dismantling-browser.mjs
WAREHOUSE_E2E=1 node tests/stage2c-owner-fault-browser.mjs
node --test tests/*unit.mjs
```

The first script explicitly publishes a local synthetic catalogue. Reseed before repeating it. The other scripts verify standalone read-only preview, explicit receipt/replay protections and synthetic HTTP faults; they must never target a remote environment.

## Next staging deployment

A separately authorized push is required; none was performed. API and Web must both deploy this revision. Alembic head remains **84d2c6fa190b**; there is **no Stage 2C migration**. Existing queue/allowlist configuration suffices.

After deployment, an owner should first read diagnostics for the actual XC60 and run **preview on real B**. Review the actual counts/errors, then publish only through an explicit owner confirmation. Open the existing XC60, inspect “Оновити каталог”, resolve any ambiguous legacy matches and explicitly save the additions. Check 33 historic IDs, 29 positive stocks, prices and receipt/sale history remain intact. Do not re-create the donor or auto-receipt candidates. This task performs none of those staging mutations.

## Completed validation

- Full backend suite: **480 passed, 1 skipped** in 616.91s. The skip is the unrelated opt-in 100k smart-search benchmark.
- After the final localized normalization guards: **60 targeted tests passed** in 144.77s (Stage 2C, canonical v3 and Stage 1.5). Counts overlap the full suite and are not additive. New regression cases include two same-model donors with disjoint plan IDs and explicit rear-camera scope through preview/approval/publication.
- Rear-view camera normalization now requires an explicit rear position. Missing/front/conflicting positions do not establish that function. Group review applies the same conditions; an owner market alias cannot rewrite a versioned universal template or silently refine its installation.
- Frontend unit tests: **349 passed**. Final production build passed.
- Real local owner/browser integration: unified 227-position XC60 workflow, group rule preview/approval, separate canonical preview/publication, reload, lost plan-save response/replay and original stock preservation pass at **1440px and 390px**.
- Updated standalone browser regressions pass at both widths: read-only preview/error/reload; explicit quantity-confirmed receipt, no repeat receipt and protected stock.
- Synthetic owner HTTP faults pass at both widths: old report hidden during 202, polling 503 recovery, stale-token 409, lost enqueue 504 recovery, reload/interruption, no duplicate publication. Current-revision retry is also checked without real catalogue mutation.
- Read-only diagnostic CLI was executed successfully on the dedicated local browser DB. `git diff --check`, one Alembic head and `alembic check` passed. No schema change is pending.

All mutation tests use local synthetic fixtures. Actual staging canonical publication and real Volvo B acceptance remain owner-controlled follow-up work.
