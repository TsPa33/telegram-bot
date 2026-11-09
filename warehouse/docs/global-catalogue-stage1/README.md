# Global Catalogue in Vehicles — stage 1

Local implementation; real MySQL/staging acceptance remains UNVERIFIED.
No push/deployment, Railway migration/import, paid calls or live stock changes.

## Targeted findings

Before this change Vehicles created donors through generic directory forms.
UnifiedCatalogue mounted PlanPartsDonorAnalysis for unsaved donors. The resolver
required complete_verified + reviewed taxonomy and otherwise proposed Base or
saved Plan.Parts. Plans persist compactly in Vehicle.dismantling_v3; detailed
article/OEM data are fetched against an immutable source SHA.

The new default uses only Catalogue. Existing source implementations remain in
code; historical lists remain separately readable. Existing donors are not rebound
or backfilled, and their stock/history/payments are not changed.

## Workflow

Vehicles → Add vehicle → manufacturer/model/generation/modification from usable
imported graphs → enter the individual donor year → Add → Dismantle vehicle →
saved types → view article/manufacturer/OEM variants. No receipt action in this
stage. Unknown generation is explicitly “Немає даних”; no inference from model
name or year. The individual vehicle year is not claimed as a catalogue fact.

Partial coverage is permitted but never promoted to complete. Unreviewed category
paths use “Потребує уточнення”; source names remain when translation is absent.
Type count and article count stay separate. No automatic OEM assignment or VIN
compatibility assertion. Article/OEM panes use existing pinned detail validation.

## Read-only API extension

- Catalogue GET /api/v1/vehicles/directory?after=0&limit=100[&car_id=...]
- Catalogue GET /api/v1/vehicles/{car_id}/plan
- Catalogue GET /api/v1/vehicles/{car_id}/articles?product_id=...&snapshot_sha=...
- Warehouse GET /api/v1/vehicles/catalogue-directory/available?after=...
- Warehouse POST /api/v1/vehicles/catalogue-directory/vehicles
- Warehouse GET/POST /api/v1/vehicles/{id}/global-dismantling

All routes are authenticated and registered in the permission allowlist. Creation
requires vehicles.create and catalog.view; plan creation requires existing
workspace ownership + dismantling.manage. Vehicle/account locks serialize retries.
Creation request keys are persisted in the same transaction as the donor. No
partial donor commit. Saved-plan reopens do not contact Catalogue. Snapshot change
before first dismantling fails explicitly instead of substituting data. Changes
to vehicle basis block subsequent creation. No Plan.Parts/Base fallback.

Directory SQL joins actual catalogue_models/catalogue_manufacturers with validated,
SHA-checked imported graphs. Entries without usable type→article links, matching
model/manufacturer identities or immutable raw versions are not offered. General
models/OEM/parts directory counts alone never imply fitment readiness. Pages are
bounded to 100; the initial frontend loads at most 100 pages and fails explicitly
if a larger directory needs server-side search. No silent truncation.

Current physical graph tables retain their historical names:
catalogue_volvo_snapshots and catalogue_volvo_versions. They are not copied or
migrated. Generic API accepts both the existing Volvo contract and the new
manufacturer-independent carpot.vehicle.v1 / carpot.vehicle.plan.v1 wire contracts.
Future imports must supply a validated exact vehicle graph; general directory rows
cannot be converted into fitment by matching OEM/article text. Existing Volvo
import allowlist remains unchanged. No automatic import of other manufacturers.

## Actual coverage evidence boundary

No Railway tool or configured Catalogue/MySQL connection is available in this
session. Consequently **no brand/model can be newly certified as imported here**.
XC90 II 107555 is the owner's previously reported real export (113 types,736
articles,175 manufacturers); this is not confirmation of its current MySQL import.
XC60 II, XC40 and all other brands remain UNVERIFIED, not asserted absent.
The directory endpoint reports actual per-modification types/articles/OEM links
and coverage when connected. Group by manufacturer/model for available modification
counts; model records without usable snapshots will not appear. Generation data
are returned only if explicitly present in the source model metadata.

## Tests

- Warehouse targeted PostgreSQL suite: 33 PASS (synthetic local dedicated test DB).
  Includes new global partial/113-type cases for manufacturer 120 and another ID,
  idempotent vehicle creation, plan retry/offline reopen, article/OEM read, old
  donor preservation, missing-fitment rejection, zero physical Parts.
- Catalogue: 16 PASS, synthetic SQL/transport/contract tests, including generic
  manufacturer directory, auth and exclusion of graphs without article links.
- TypeScript/Vite build: PASS; existing bundle-size advisory remains.
- Chromium 1440/390: PASS with built UI + local authentication + intercepted
  synthetic directory/plan responses. Select/add/dismantle,113 types, article/OEM
  panel, reload, zero Plan.Parts/Base calls, JS errors or page horizontal overflow.
  Screenshots under screenshots/ are explicitly synthetic, not real MySQL proof.

Local DB tests use only localhost:55440/warehouse_volvo_integration_test, and the
existing test fixtures apply migrations and truncate only that dedicated test DB.
They do not prove real MySQL grants, actual imported counts or staging behavior.

## Remaining acceptance

Connect read-only Catalogue to enumerate actual brands/models and per-modification
coverage; run the owner's real 107555 scenario and verify the snapshot type count.
If no usable import exists the selector must remain empty/unavailable, without a
paid fallback. Separate approval is required for deployment or data import.
No new PostgreSQL/MySQL schema migration is introduced by this change.


## Changed areas

Catalogue app/contract/tests; Warehouse unified API/service, explicit permission
registry; Vehicles add form, default catalogue flow, vehicle modification label;
targeted backend/browser tests. Existing stock, finance and payment handlers are
unchanged. Deploy Catalogue extension before Warehouse to retain compatibility;
legacy Volvo article endpoint remains the default for legacy pinned snapshots.
New generic graphs use the universal endpoint. Deploy/import remains unauthorized.

Confirmed modification description is stored as a modification label, never
misrepresented as a normalized engine specification. Raw confirmed source
attributes are retained with source selection (up to100 entries); mapping them to
normalized engine/fuel/transmission fields needs the actual attribute dictionary.
Until verified, these normalized fields remain unknown; no model-name inference.

Frontend list is paginated25 types per page. Browser checks passed at1440/390 after
pagination, with all113 synthetic types preserved in saved payload. The initial
browser locator issue was corrected with explicit accessible select labels;
final runs pass. An initial Catalogue pytest invocation from repository root hit
the unrelated Telegram package __init__; running with catalogue/tests root and
importlib mode passes. These are not staging/runtime failures.
